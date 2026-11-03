from __future__ import annotations

from io import BytesIO

from fastapi import HTTPException, status

MAX_IMAGE_BYTES = 10 * 1024 * 1024
SUPPORTED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff", "image/bmp"}


def extract_invoice_text(image_bytes: bytes, content_type: str | None) -> str:
    """Extract text from an invoice image without persisting the uploaded bytes."""
    if not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded image is empty")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Invoice images must be 10 MB or smaller",
        )
    if content_type not in SUPPORTED_CONTENT_TYPES:
        supported = ", ".join(sorted(SUPPORTED_CONTENT_TYPES))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type. Use one of: {supported}",
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
            ocr_image = image.convert("RGB")
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

    try:
        import pytesseract

        text = pytesseract.image_to_string(ocr_image, config="--psm 6")
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
