"""Read-only Day 3 live-readiness checker for VyaparKitaab (never prints secret values)."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.cores.config import Settings

_WEAK_SECRET_KEYS = {
    "",
    "change-me-to-a-secure-random-key",
    "generate-a-strong-secret-key-at-least-32-chars",
    "ci-secret",
}


def _safe_db_target(raw_url: str) -> str:
    """Format DB URL showing only scheme, host, port, and database name (no credentials)."""
    parsed = urlsplit(raw_url)
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    db_name = parsed.path or "/vyaapardb"
    return f"{parsed.scheme or 'postgresql'}://{host}{port}{db_name}"


def _installed_tesseract_langs() -> list[str]:
    if not shutil.which("tesseract"):
        return []
    try:
        import pytesseract

        return sorted(pytesseract.get_languages(config=""))
    except (ImportError, OSError):
        return []


def _status_line(level: str, label: str, detail: str) -> None:
    print(f"[{level:<8}] {label:<32} {detail}")


def main() -> int:
    env_path = REPO_ROOT / ".env"
    try:
        cfg = Settings(_env_file=env_path if env_path.exists() else None)
    except (ValidationError, OSError, ValueError) as exc:
        _status_line("WARN", "Configuration (.env)", f"Could not load settings cleanly: {type(exc).__name__}")
        return 1

    print("=== VyaparKitaab Live Readiness Check ===\n")

    # 1. Local OCR & PDF Runtime
    print("-- Local OCR & PDF Runtime --")
    langs = _installed_tesseract_langs()
    if shutil.which("tesseract"):
        has_hin = "hin" in langs
        _status_line(
            "OK" if has_hin else "WARN",
            "Tesseract OCR",
            f"installed (langs: {', '.join(langs) or 'none'})"
            + ("" if has_hin else " -> install Hindi pack: sudo apt install -y tesseract-ocr-hin"),
        )
    else:
        _status_line("WARN", "Tesseract OCR", "binary missing from PATH")

    pdftotext_ok = bool(shutil.which("pdftotext"))
    _status_line(
        "OK" if pdftotext_ok else "WARN",
        "Poppler pdftotext",
        "installed" if pdftotext_ok else "missing (install poppler-utils)",
    )

    pypdf_ok = importlib.util.find_spec("pypdf") is not None
    _status_line(
        "OK" if pypdf_ok else "WARN",
        "pypdf (in-memory PDF unlock)",
        "installed" if pypdf_ok else 'missing -> run: .venv/bin/pip install "pypdf>=4"',
    )

    # 2. Core Security & Database
    print("\n-- Core Security & Database --")
    _status_line("OK" if cfg.DATABASE_URL.strip() else "WARN", "DATABASE_URL", _safe_db_target(cfg.DATABASE_URL))

    secret_val = cfg.SECRET_KEY.strip()
    secret_strong = secret_val not in _WEAK_SECRET_KEYS and len(secret_val) >= 32
    _status_line(
        "OK" if secret_strong else "WARN",
        "SECRET_KEY",
        f"strong ({len(secret_val)} chars)" if secret_strong else f"weak or short ({len(secret_val)} chars; recommend >= 32)",
    )

    enc_set = bool(cfg.ENCRYPTION_KEY.strip())
    is_prod = cfg.ENV.strip().lower() == "production"
    _status_line(
        "OK" if enc_set else ("WARN" if is_prod else "OPTIONAL"),
        "ENCRYPTION_KEY",
        "set" if enc_set else "unset (required for stable production PII encryption; auto-generated on Render)",
    )

    origins = cfg.ALLOWED_ORIGINS
    wildcard_in_prod = is_prod and "*" in origins
    _status_line(
        "WARN" if wildcard_in_prod else "OK",
        "ALLOWED_ORIGINS",
        f"{', '.join(origins)}" + (" (restrict '*' in production!)" if wildcard_in_prod else ""),
    )

    # 3. Live Integrations
    print("\n-- Live Integrations --")
    smtp_ready = all(
        bool(v.strip()) for v in (cfg.SMTP_USER, cfg.SMTP_PASSWORD, cfg.SMTP_FROM_EMAIL)
    )
    _status_line(
        "OK" if (cfg.OTP_PROVIDER == "smtp_email" and smtp_ready) else "WARN",
        "Gmail SMTP OTP",
        f"provider={cfg.OTP_PROVIDER}, host={cfg.SMTP_HOST}, credentials={'SET' if smtp_ready else 'INCOMPLETE'}",
    )

    rzp_ready = all(
        bool(v.strip()) for v in (cfg.PAYMENT_KEY_ID, cfg.PAYMENT_KEY_SECRET, cfg.PAYMENT_WEBHOOK_SECRET)
    )
    _status_line(
        "OK" if (cfg.PAYMENT_GATEWAY == "razorpay" and rzp_ready) else "WARN",
        "Razorpay Payments",
        f"gateway={cfg.PAYMENT_GATEWAY}, keys={'SET' if rzp_ready else 'INCOMPLETE'}",
    )

    gemini_set = bool(cfg.GEMINI_API_KEY.strip())
    _status_line(
        "OK" if gemini_set else "OPTIONAL",
        "Handwritten Hindi Vision",
        f"model={cfg.OCR_GEMINI_MODEL}, GEMINI_API_KEY={'SET' if gemini_set else 'UNSET (falls back to Tesseract)'}",
    )

    setu_ready = bool(cfg.SETU_AA_CLIENT_ID.strip() and cfg.SETU_AA_CLIENT_SECRET.strip())
    _status_line(
        "OK" if (cfg.BANK_DATA_PROVIDER == "setu_aa" and setu_ready) else "OPTIONAL",
        "Setu Account Aggregator",
        f"provider={cfg.BANK_DATA_PROVIDER}, credentials={'SET' if setu_ready else 'UNSET (statement upload & bridge active)'}",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
