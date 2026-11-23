from __future__ import annotations

import base64
import logging
import shutil
from io import BytesIO
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.cores.config import settings
from app.services.statement_importer import _extract_text_from_pdf_bytes

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff",
    "image/bmp",
}

_GEMINI_RECEIPT_PROMPT = (
    "You are an expert Indian kirana/GST receipt OCR reader specializing in handwritten Hindi "
    "(Devanagari), printed Hindi, Hinglish, and English bills. Transcribe all readable text from "
    "this receipt image cleanly into plain lines:\n"
    "- Put store/merchant name on the first line.\n"
    "- Keep Bill/Invoice No, Date, and GSTIN if present.\n"
    "- Put each item on its own line formatted as: <Item Name & Qty> ₹<Amount>\n"
    "- Put the final total clearly formatted as: Total: ₹<Amount>\n"
    "- Convert any Devanagari digits (०-९) into standard digits (0-9).\n"
    "- Output only the transcribed receipt text without markdown fences or commentary."
)


def _get_installed_tesseract_langs() -> list[str]:
    if not shutil.which("tesseract"):
        return []
    try:
        import pytesseract

        return sorted(pytesseract.get_languages(config=""))
    except (ImportError, OSError, pytesseract.pytesseract.TesseractError):
        return []


def _resolve_tesseract_lang(requested_lang: str | None) -> str:
    installed = set(_get_installed_tesseract_langs())
    req = (requested_lang or settings.OCR_DEFAULT_LANG or "auto").strip().lower()
    wants_hindi = req in ("hin", "hi", "hindi", "hin+eng", "eng+hin", "auto")
    if wants_hindi and "hin" in installed:
        return "hin+eng" if "eng" in installed else "hin"
    return "eng"


def get_ocr_capabilities() -> dict[str, Any]:
    """Reports honest runtime OCR capabilities (offline Hindi Tesseract vs. Gemini Handwriting Vision)."""
    installed = _get_installed_tesseract_langs()
    return {
        "tesseract_available": bool(shutil.which("tesseract")),
        "installed_languages": installed,
        "hindi_offline_ready": "hin" in installed,
        "handwriting_vision_ready": bool((settings.GEMINI_API_KEY or "").strip()),
        "supported_modes": ["auto", "eng", "hin", "handwriting"],
    }


def preprocess_invoice_image(image, handwriting: bool = False):
    """
    Production preprocessing for camera/scanned receipts and handwritten Hindi bills:
    1. Apply EXIF orientation transpose.
    2. Convert to grayscale luminance ('L').
    3. Upscale low-resolution photos (< 900px, or < 1200px for handwriting) for crisp matras & digits.
    4. For handwritten paper photos, normalize uneven shadow/lighting via median background division.
    5. Apply autocontrast and edge sharpening.
    """
    from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

    oriented = ImageOps.exif_transpose(image)
    gray = oriented.convert("L")
    w, h = gray.size
    min_target = 1200 if handwriting else 900
    if min(w, h) < min_target and max(w, h) * 2 <= 5000:
        resampling = getattr(Image, "Resampling", Image).LANCZOS
        gray = gray.resize((w * 2, h * 2), resample=resampling)

    if handwriting:
        # Remove uneven phone-camera paper shadows while preserving handwritten Devanagari strokes
        bg = gray.filter(ImageFilter.MedianFilter(size=25))
        diff = ImageChops.subtract(bg, gray)
        norm = ImageOps.invert(diff)
        contrasted = ImageOps.autocontrast(norm, cutoff=2)
        return ImageEnhance.Sharpness(contrasted).enhance(1.8)

    contrasted = ImageOps.autocontrast(gray, cutoff=1)
    return ImageEnhance.Sharpness(contrasted).enhance(1.5)


def _extract_with_gemini_vision(image_bytes: bytes, content_type: str, lang: str, handwriting: bool) -> str | None:
    """Optional HTTPS multimodal vision OCR for handwritten Hindi/Devanagari receipts."""
    api_key = (settings.GEMINI_API_KEY or "").strip()
    if not api_key:
        return None

    model = (settings.OCR_GEMINI_MODEL or "gemini-2.5-flash").strip()
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = _GEMINI_RECEIPT_PROMPT
    if handwriting:
        prompt += "\nFocus carefully on handwritten Devanagari matras and scribbled totals."
    elif lang in ("hin", "hi", "hin+eng", "eng+hin"):
        prompt += "\nPrioritize accurate Hindi (Devanagari) and English text recognition."

    mime_type = content_type if content_type in SUPPORTED_CONTENT_TYPES and content_type != "application/pdf" else "image/jpeg"
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {"temperature": 0.1},
    }
    try:
        resp = httpx.post(
            endpoint,
            params={"key": api_key},
            json=payload,
            timeout=25.0,
        )
        if resp.status_code != 200:
            logger.warning("Gemini Vision OCR returned status %s; falling back to Tesseract", resp.status_code)
            return None
        data = resp.json()
        candidates = data.get("candidates") or []
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        extracted = "\n".join(str(p.get("text", "")) for p in parts if p.get("text")).strip()
        return extracted or None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("Gemini Vision OCR request failed (%s); falling back to Tesseract", type(exc).__name__)
        return None


def extract_invoice_text(
    image_bytes: bytes,
    content_type: str | None,
    lang: str = "auto",
    handwriting: bool = False,
) -> str:
    """Extract text from an invoice image or PDF without persisting the uploaded bytes."""
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Invoice files must be 10 MB or smaller",
        )
    is_pdf = content_type == "application/pdf" or image_bytes.lstrip().startswith(b"%PDF")
    if is_pdf:
        pdf_text = _extract_text_from_pdf_bytes(image_bytes).strip()
        if not pdf_text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No readable text was found in the uploaded PDF invoice",
            )
        return pdf_text
    if content_type not in SUPPORTED_CONTENT_TYPES:
        supported = ", ".join(sorted(SUPPORTED_CONTENT_TYPES))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type. Use one of: {supported}",
        )

    try:
        from PIL import Image, UnidentifiedImageError

        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
            if image.width > 5000 or image.height > 5000:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Invoice image dimensions must not exceed 5000 by 5000 pixels",
                )
            ocr_image = preprocess_invoice_image(image, handwriting=handwriting)
    except HTTPException:
        raise
    except UnidentifiedImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a valid image",
        ) from exc
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR image support is not installed on the server",
        ) from exc

    norm_lang = (lang or settings.OCR_DEFAULT_LANG or "auto").strip().lower()
    if (handwriting or norm_lang in ("hin", "hi", "hindi", "hin+eng", "eng+hin")) and (settings.GEMINI_API_KEY or "").strip():
        vision_text = _extract_with_gemini_vision(image_bytes, content_type or "image/jpeg", norm_lang, handwriting)
        if vision_text:
            return vision_text

    try:
        import pytesseract

        tess_lang = _resolve_tesseract_lang(norm_lang)
        psm_sequence = ("--oem 3 --psm 6", "--oem 3 --psm 11", "--oem 3 --psm 4") if handwriting else ("--oem 3 --psm 6", "--oem 3 --psm 4")
        text = ""
        for cfg in psm_sequence:
            text = pytesseract.image_to_string(ocr_image, lang=tess_lang, config=cfg)
            if text.strip():
                break
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR support is not installed on the server",
        ) from exc
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR engine is not available on the server",
        ) from exc

    cleaned_text = text.strip()
    if not cleaned_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No readable text was found in the invoice image",
        )
    return cleaned_text
