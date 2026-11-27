"""Redacts credentials and PII from access-log URLs (uvicorn.access / any logger)."""
from __future__ import annotations

import logging
import re

_SENSITIVE_QS = re.compile(
    r"(?i)([?&](?:otp|token|access_token|refresh_token|password|pdf_password|phone|email|signature)=)[^&\s\"']*"
)
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+")


def redact_text(text: str) -> str:
    text = _SENSITIVE_QS.sub(r"\1[REDACTED]", text)
    return _BEARER.sub(r"\1[REDACTED]", text)


class RedactingFilter(logging.Filter):
    """Scrubs sensitive query-string values from log messages and format args."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact_text(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: redact_text(v) if isinstance(v, str) else v for k, v in record.args.items()}
        return True


def install_log_redaction() -> None:
    flt = RedactingFilter()
    for name in ("uvicorn.access", "uvicorn.error", "uvicorn", "httpx", "httpcore"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, RedactingFilter) for f in lg.filters):
            lg.addFilter(flt)
    # httpx logs full request URLs at INFO (may contain Razorpay/Gemini keys in query strings)
    logging.getLogger("httpx").setLevel(logging.WARNING)
