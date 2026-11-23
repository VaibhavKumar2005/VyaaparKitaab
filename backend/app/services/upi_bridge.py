"""
Zero-Credential UPI Auto-Sync Bridge Service.

Implements real-world client-side / webhook ingestion patterns for Google Pay,
Paytm, PhonePe, and bank UPI alerts without ever requesting, storing, or leaking
UPI PINs, bank netbanking passwords, or Gmail/Google OAuth credentials:
  1. Scoped, revocable per-user HMAC ingest tokens (X-Ingest-Token header only).
  2. Strict pre-persistence OTP / PIN / CVV blocker & raw account number scrubber.
  3. Idempotent ingestion into BankTransaction + live SSE stream broadcast.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.config import settings
from app.models.banking_consent import PaymentWebhookEvent
from app.services.classifier import classify_hierarchical, to_legacy_bank_label
from app.services.event_bus import publish_event
from app.services.payment_recorder import detect_upi_app
from app.services.statement_importer import classify_transaction, import_statement_transactions

APP_PACKAGE_MAP: dict[str, str] = {
    "com.google.android.apps.nbu.paisa.user": "Google Pay",
    "com.google.android.apps.walletnfcrel": "Google Pay",
    "net.one97.paytm": "Paytm",
    "com.paytm.merchants": "Paytm",
    "com.phonepe.app": "PhonePe",
    "com.phonepe.app.business": "PhonePe",
    "in.org.npci.upiapp": "BHIM UPI",
    "in.amazon.mshop.android.shopping": "Amazon Pay",
    "com.dreamplug.androidapp": "CRED",
    "com.whatsapp": "WhatsApp Pay",
    "gmail_apps_script": "Gmail Auto-Sync",
    "ios_shortcut": "iOS Shortcut",
    "android_sms": "SMS Bridge",
}

_OTP_SECURITY_RE = re.compile(
    r"\b(?:otp|one[\s-]?time[\s-]?password|verification\s+code|security\s+code|"
    r"auth(?:entication)?\s+code|login\s+code|passcode|mpin|upi\s*pin|atm\s*pin|tpin|cvv|cvc)\b",
    re.IGNORECASE,
)
_DO_NOT_SHARE_AUTH_RE = re.compile(
    r"(?:\bdo\s+not\s+share\b.*\b(?:code|otp|pin|password|cvv)\b|"
    r"\b(?:code|otp|pin|password|cvv)\b.*\bdo\s+not\s+share\b)",
    re.IGNORECASE,
)
_PROMO_SPAM_RE = re.compile(
    r"\b(?:scratch\s+card|win\s+up\s+to|cashback\s+offer|flat\s+\d+%\s+off|apply\s+now|loan\s+approved)\b",
    re.IGNORECASE,
)
_TXN_CUE_RE = re.compile(
    r"\b(?:paid|received|debited|credited|sent|withdrawn|deposited|transferred|upi/dr|upi/cr)\b",
    re.IGNORECASE,
)
_CREDIT_CUE_RE = re.compile(
    r"\b(?:credited|received|paid\s+you|sent\s+you|added\s+to|refund\s+from|cashback\s+credited|upi/cr/)\b",
    re.IGNORECASE,
)
_DEBIT_CUE_RE = re.compile(
    r"\b(?:debited|paid\s+to|paid|sent\s+to|sent|spent|transferred\s+to|withdrawn|purchase\s+at|upi/dr/)\b",
    re.IGNORECASE,
)
_AMOUNT_INR_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_AMOUNT_VERB_RE = re.compile(
    r"\b(?:paid|received|debited|credited|sent)\s+(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)
_UTR_LABELED_RE = re.compile(
    r"(?:utr|upi\s*ref(?:\s*no)?|ref(?:\s*no)?|upi\s*transaction\s*id|transaction\s*id|txn\s*id)\s*[:#\-]?\s*([A-Z0-9]{8,24})",
    re.IGNORECASE,
)
_UTR_SLASH_RE = re.compile(r"UPI/(?:DR|CR)/(\d{10,16})", re.IGNORECASE)
_UTR_12DIGIT_RE = re.compile(r"\b(\d{12})\b")

# Scrubbing patterns
_ACCOUNT_RAW_RE = re.compile(
    r"(\b(?:a/c|ac|acct?|account|card)\s*(?:no\.?|number|ending|#)?\s*[:\-]?\s*)"
    r"([x*\-\s\d]{4,18}?)(\d{4})\b",
    re.IGNORECASE,
)
_CARD_GROUPED_RE = re.compile(r"\b(?:\d{4}[-\s]?){3}(\d{4})\b")
_LONG_RAW_DIGITS_RE = re.compile(r"\b\d{13,19}\b")
_MASKED_ACC_EXTRACT_RE = re.compile(r"(?:[x*]{2,}[-\s]*|XXXX-XXXX-)(\d{4})\b", re.IGNORECASE)
_SECRET_KV_RE = re.compile(
    r"\b(password|passwd|mpin|upi[_\s]?pin|cvv|cvc|bearer)\s*[:=]\s*[^\s,;]+",
    re.IGNORECASE,
)
_TO_FROM_COUNTERPARTY_RE = re.compile(
    r"\b(?:paid\s+to|sent\s+to|transferred\s+to|received\s+from|from|to)\s+"
    r"([A-Za-z0-9&._@\- ]{2,45}?)(?=\s+(?:via|using|on|ref|utr|upi|from|at|for|with|a/c)\b|\s*[.,;\n—–|]|$)",
    re.IGNORECASE,
)
_PAID_YOU_RE = re.compile(r"^\s*([A-Za-z0-9&._\- ]{2,40}?)\s+(?:paid|sent)\s+you\b", re.IGNORECASE)


def _bridge_signing_key() -> bytes:
    raw_secret = (settings.ENCRYPTION_KEY or settings.SECRET_KEY or "vyaparkitaab-dev-bridge").encode("utf-8")
    return hashlib.sha256(b"vk-upi-bridge-v1:" + raw_secret).digest()


def _config_event_id(user_id: uuid.UUID | str) -> str:
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    return f"upi_bridge_cfg:{uid}"


def mint_scoped_ingest_token(user_id: uuid.UUID | str, jti: str | None = None) -> tuple[str, str]:
    """Mint a deterministic HMAC-signed scoped ingest token paired with a unique jti."""
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    token_jti = jti or secrets.token_urlsafe(12)
    payload_bytes = f"{uid}:{token_jti}".encode()
    b64_payload = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    sig = hmac.new(_bridge_signing_key(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return f"vk_upi_{b64_payload}.{sig}", token_jti


def verify_scoped_ingest_token_signature(token: str) -> tuple[uuid.UUID, str] | None:
    """Verify cryptographic signature of a scoped ingest token without trusting payload."""
    if not token or not token.startswith("vk_upi_") or "." not in token:
        return None
    body = token[len("vk_upi_") :]
    parts = body.split(".", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None

    b64_payload, provided_sig = parts
    expected_sig = hmac.new(_bridge_signing_key(), b64_payload.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(provided_sig, expected_sig):
        return None

    padded = b64_payload + "=" * ((4 - len(b64_payload) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        uid_str, jti = decoded.split(":", 1)
        uid = uuid.UUID(uid_str)
    except (ValueError, UnicodeDecodeError):
        return None

    if not jti:
        return None
    return uid, jti


def mask_token_preview(token: str) -> str:
    if len(token) <= 14:
        return "vk_upi_***"
    return f"{token[:10]}...{token[-6:]}"


def is_security_or_otp_message(text: str) -> bool:
    """Return True if the alert contains OTPs, PINs, CVVs, or promo non-transactional noise."""
    if not text:
        return False
    if _OTP_SECURITY_RE.search(text) or _DO_NOT_SHARE_AUTH_RE.search(text):
        return True
    return bool(_PROMO_SPAM_RE.search(text) and not _TXN_CUE_RE.search(text))


def scrub_sensitive_text(text: str) -> tuple[str, str]:
    """
    Remove raw bank account numbers, card numbers, and accidental secret key/value pairs
    before persisting any notification/SMS/email text. Returns (clean_text, masked_acc).
    """
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    cleaned = _SECRET_KV_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", cleaned)
    cleaned = _ACCOUNT_RAW_RE.sub(lambda m: f"{m.group(1)}XXXX-XXXX-{m.group(3)}", cleaned)
    cleaned = _CARD_GROUPED_RE.sub(lambda m: f"XXXX-XXXX-{m.group(1)}", cleaned)
    cleaned = _LONG_RAW_DIGITS_RE.sub(lambda m: f"XXXX-XXXX-{m.group(0)[-4:]}", cleaned)

    acc_match = _MASKED_ACC_EXTRACT_RE.search(cleaned)
    masked_acc = f"XXXX-XXXX-{acc_match.group(1)}" if acc_match else "Account Masked"
    return cleaned[:320], masked_acc


def _resolve_app_name(app_hint: str | None, combined_text: str) -> str:
    low_hint = (app_hint or "").strip().lower()
    if low_hint in APP_PACKAGE_MAP:
        return APP_PACKAGE_MAP[low_hint]
    for pkg, friendly in APP_PACKAGE_MAP.items():
        if pkg in low_hint:
            return friendly

    # Delegate VPA handle / generic channel detection to payment_recorder.detect_upi_app
    for token in combined_text.split():
        if "@" in token:
            detected = detect_upi_app(token.strip(".,;:()[]"), "UPI")
            if detected not in ("UPI", "Other UPI"):
                return detected

    low_text = combined_text.lower()
    if "google pay" in low_text or "gpay" in low_text:
        return "Google Pay"
    if "paytm" in low_text:
        return "Paytm"
    if "phonepe" in low_text:
        return "PhonePe"
    if "bhim" in low_text:
        return "BHIM UPI"
    if app_hint and app_hint.strip() and "." not in app_hint and low_hint not in ("android_notification", "webhook"):
        return app_hint.strip()[:50]
    return "UPI Bridge"


def _extract_amount(text: str) -> float:
    for pattern in (_AMOUNT_INR_RE, _AMOUNT_VERB_RE):
        match = pattern.search(text)
        if match:
            try:
                val = float(match.group(1).replace(",", ""))
                if val > 0:
                    return round(val, 2)
            except ValueError:
                continue
    return 0.0


def _extract_utr(text: str) -> str | None:
    for pattern in (_UTR_LABELED_RE, _UTR_SLASH_RE, _UTR_12DIGIT_RE):
        match = pattern.search(text)
        if match:
            candidate = match.group(1).strip()
            # Guard against matching a 4-digit masked account tail or year
            if len(candidate) >= 8:
                return candidate
    return None


def _extract_counterparty_override(title: str, scrubbed_text: str) -> str | None:
    paid_you = _PAID_YOU_RE.search(scrubbed_text)
    if paid_you:
        name = paid_you.group(1).strip(" :-")
        if name and not name.lower().startswith(("you", "your", "rs", "inr")):
            return name

    for match in _TO_FROM_COUNTERPARTY_RE.finditer(scrubbed_text):
        candidate = match.group(1).strip(" :-")
        low = candidate.lower()
        if candidate and not any(
            bad in low for bad in ("your ", "a/c", "acct", "account", "hdfc bank", "sbi ", "icici ", "axis bank", "kotak")
        ):
            return candidate

    clean_title = (title or "").strip()
    if (
        clean_title
        and 2 <= len(clean_title) <= 45
        and not any(
            k in clean_title.lower()
            for k in ("paid", "received", "debited", "credited", "google pay", "paytm", "phonepe", "₹", "rs")
        )
    ):
        return clean_title
    return None


def parse_upi_alert_payload(
    *,
    message: str = "",
    title: str = "",
    app_package: str = "",
    source_channel: str = "android_notification",
    txn_id: str | None = None,
    timestamp: datetime | None = None,
    amount: float | None = None,
    direction: str | None = None,
    counterparty: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
) -> dict[str, Any]:
    """
    Thin connector parser & sanitizer for optional external UPI webhook/alert events.
    Filters OTP/security codes, scrubs sensitive credentials, normalizes into the
    canonical schema, and classifies through `classifier.classify_hierarchical`.
    """
    raw_combined = f"{title.strip()} — {message.strip()}".strip(" —")
    if not raw_combined and not (amount and amount > 0 and direction):
        return {"accepted": False, "reason": "empty_alert_payload"}

    if raw_combined and is_security_or_otp_message(raw_combined):
        return {"accepted": False, "reason": "otp_or_security_message_ignored"}

    scrubbed_text, masked_acc = scrub_sensitive_text(raw_combined or (counterparty or "UPI Bridge Event"))
    resolved_amount = round(float(amount), 2) if (amount is not None and amount > 0) else _extract_amount(scrubbed_text)
    if resolved_amount <= 0:
        return {"accepted": False, "reason": "no_transaction_amount_detected"}

    # Determine direction (prefer explicit normalized field, else cue regex)
    if direction and direction.strip().upper() in ("CREDIT", "DEBIT"):
        tx_type = direction.strip().upper()
    elif _CREDIT_CUE_RE.search(scrubbed_text):
        tx_type = "CREDIT"
    elif _DEBIT_CUE_RE.search(scrubbed_text):
        tx_type = "DEBIT"
    else:
        return {"accepted": False, "reason": "no_credit_or_debit_direction"}

    dt = timestamp.astimezone(UTC) if timestamp and timestamp.tzinfo else (timestamp.replace(tzinfo=UTC) if timestamp else datetime.now(UTC))
    date_str = dt.strftime("%Y-%m-%d")

    upper_text = scrubbed_text.upper()
    mode = "NEFT" if "NEFT" in upper_text else ("IMPS" if "IMPS" in upper_text else ("RTGS" if "RTGS" in upper_text else "UPI"))

    app_hint = _resolve_app_name(app_package or source_channel, scrubbed_text)
    _, extracted_party, detected_app, vpa = classify_transaction(scrubbed_text, tx_type, mode, app_hint)

    resolved_party = (counterparty or "").strip() or extracted_party
    if not counterparty:
        explicit_party = _extract_counterparty_override(title, scrubbed_text)
        if explicit_party and (
            resolved_party in ("UPI Merchant", "UPI Peer", "Merchant / Peer", "Bank Transfer")
            or not upper_text.startswith(("UPI/", "IMPS/", "NEFT/", "RTGS/"))
        ):
            resolved_party = explicit_party[:150]

    canon_cat, canon_subcat, _ = classify_hierarchical(
        text=scrubbed_text,
        counterparty=resolved_party,
        direction=tx_type,
        amount=resolved_amount,
        explicit_category=category,
        explicit_subcategory=subcategory,
        source_type="upi_bridge",
    )
    legacy_category = to_legacy_bank_label(canon_cat, canon_subcat, tx_type)

    extracted_ref = (txn_id or "").strip() or _extract_utr(scrubbed_text)
    if not extracted_ref:
        digest = hashlib.sha1(
            f"{date_str}|{resolved_amount:.2f}|{tx_type}|{resolved_party.lower()}".encode()
        ).hexdigest()[:12]
        extracted_ref = f"BRIDGE_{date_str.replace('-', '')}_{digest}"

    return {
        "accepted": True,
        "transaction": {
            "txn_id": extracted_ref[:120],
            "timestamp": dt,
            "date": date_str,
            "amount": resolved_amount,
            "type": tx_type,
            "mode": mode,
            "app": (detected_app or app_hint)[:50],
            "vpa": vpa[:150] if vpa else None,
            "narration": scrubbed_text,
            "category": legacy_category[:100],
            "canonical_category": canon_cat,
            "subcategory": canon_subcat,
            "counterparty": resolved_party[:150],
            "masked_acc": masked_acc[:50],
        },
    }


def build_automation_templates(token: str, api_base_url: str) -> dict[str, Any]:
    """Generate ready-to-copy client-side templates that never share account passwords."""
    clean_base = api_base_url.rstrip("/")
    endpoint = f"{clean_base}/api/v1/banking/upi-bridge/ingest"

    apps_script = (
        f'const VK_WEBHOOK_URL = "{endpoint}";\n'
        f'const VK_INGEST_TOKEN = "{token}";\n\n'
        "function syncUpiAlertsToVyaparKitaab() {\n"
        '  const label = GmailApp.getUserLabelByName("vk_synced") || GmailApp.createLabel("vk_synced");\n'
        '  const threads = GmailApp.search(\'from:(googlepay-noreply@google.com OR alerts@paytm.com OR alerts@hdfcbank.net) newer_than:2d -label:vk_synced\', 0, 20);\n'
        "  for (const thread of threads) {\n"
        "    for (const msg of thread.getMessages()) {\n"
        '      const body = (msg.getPlainBody() || "").replace(/\\b\\d{13,18}\\b/g, "XXXX-XXXX").slice(0, 350);\n'
        "      const payload = {\n"
        '        source_channel: "gmail_apps_script",\n'
        '        app_package: "gmail_apps_script",\n'
        "        title: msg.getSubject(),\n"
        "        message: body,\n"
        "        timestamp: msg.getDate().toISOString()\n"
        "      };\n"
        "      UrlFetchApp.fetch(VK_WEBHOOK_URL, {\n"
        '        method: "post",\n'
        '        contentType: "application/json",\n'
        '        headers: { "X-Ingest-Token": VK_INGEST_TOKEN },\n'
        "        payload: JSON.stringify(payload),\n"
        "        muteHttpExceptions: true\n"
        "      });\n"
        "    }\n"
        "    thread.addLabel(label);\n"
        "  }\n"
        "}"
    )

    curl_example = (
        f'curl -X POST "{endpoint}" \\\n'
        '  -H "Content-Type: application/json" \\\n'
        f'  -H "X-Ingest-Token: {token}" \\\n'
        '  -d \'{"app_package":"com.google.android.apps.nbu.paisa.user","title":"Paid ₹450.00 to Blue Tokai Coffee","message":"Paid via HDFC Bank A/C XX4821. UPI Ref: 431789123456","source_channel":"android_notification"}\''
    )

    return {
        "webhook_endpoint": "/api/v1/banking/upi-bridge/ingest",
        "full_webhook_url": endpoint,
        "header_name": "X-Ingest-Token",
        "supported_packages": [
            "com.google.android.apps.nbu.paisa.user (Google Pay)",
            "net.one97.paytm (Paytm)",
            "com.phonepe.app (PhonePe)",
            "in.org.npci.upiapp (BHIM UPI)",
        ],
        "android_payload_template": json.dumps(
            {
                "source_channel": "android_notification",
                "app_package": "{notification_app_package}",
                "title": "{notification_title}",
                "message": "{notification_text}",
            },
            indent=2,
        ),
        "gmail_apps_script": apps_script,
        "ios_shortcut_steps": [
            "Open Apple Shortcuts -> Automation -> '+' -> Message / Transaction.",
            'Trigger: When Message contains "UPI" or "debited" or "credited" (Run Immediately).',
            f"Action: Get Contents of URL -> {endpoint} (Method: POST).",
            "Headers: Content-Type = application/json, X-Ingest-Token = <your scoped token>.",
            'JSON Body: { "source_channel": "ios_shortcut", "title": "UPI SMS", "message": [Shortcut Input] }.',
        ],
        "curl_test_command": curl_example,
    }


async def _get_config_record(db: AsyncSession, user_id: uuid.UUID) -> PaymentWebhookEvent | None:
    res = await db.execute(
        select(PaymentWebhookEvent).where(
            PaymentWebhookEvent.event_id == _config_event_id(user_id),
            PaymentWebhookEvent.event_type == "upi_bridge_config",
        )
    )
    return res.scalar_one_or_none()


def _format_bridge_config_response(token: str, meta: dict[str, Any], api_base_url: str) -> dict[str, Any]:
    return {
        "status": meta.get("status", "ACTIVE"),
        "ingest_token": token,
        "masked_token": mask_token_preview(token),
        "rotated_at": meta.get("rotated_at"),
        "ingest_count": meta.get("ingest_count", 0),
        "last_ingest_at": meta.get("last_ingest_at"),
        "last_app": meta.get("last_app"),
        "templates": build_automation_templates(token, api_base_url),
    }


async def get_or_create_bridge_config(
    db: AsyncSession,
    user_id: uuid.UUID | str,
    api_base_url: str = "",
) -> dict[str, Any]:
    """Return active scoped bridge configuration (recomputing token cleanly from jti)."""
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    record = await _get_config_record(db, uid)
    now_iso = datetime.now(UTC).isoformat()

    if record is None:
        token, jti = mint_scoped_ingest_token(uid)
        meta = {
            "active_jti": jti,
            "status": "ACTIVE",
            "rotated_at": now_iso,
            "ingest_count": 0,
            "last_ingest_at": None,
            "last_app": None,
        }
        await db.execute(
            pg_insert(PaymentWebhookEvent)
            .values(
                id=uuid.uuid4(),
                event_id=_config_event_id(uid),
                event_type="upi_bridge_config",
                payload=json.dumps(meta),
                status="ACTIVE",
            )
            .on_conflict_do_nothing(index_elements=["event_id"])
        )
        await db.commit()
        record = await _get_config_record(db, uid)
        if record is not None:
            meta = json.loads(record.payload or "{}")
            jti = meta.get("active_jti") or jti
            token, _ = mint_scoped_ingest_token(uid, jti=jti)
    else:
        meta = json.loads(record.payload or "{}")
        jti = meta.get("active_jti")
        if record.status != "REVOKED" and not jti:
            token, jti = mint_scoped_ingest_token(uid)
            meta["active_jti"] = jti
            meta["status"] = "ACTIVE"
            meta["rotated_at"] = now_iso
            record.payload = json.dumps(meta)
            record.status = "ACTIVE"
            await db.commit()
        elif record.status == "REVOKED" or not jti:
            return {
                "status": "REVOKED",
                "ingest_token": "",
                "masked_token": "REVOKED",
                "rotated_at": meta.get("rotated_at"),
                "ingest_count": meta.get("ingest_count", 0),
                "last_ingest_at": meta.get("last_ingest_at"),
                "last_app": meta.get("last_app"),
                "templates": build_automation_templates("<ROTATE_TOKEN_FIRST>", api_base_url),
            }
        else:
            token, _ = mint_scoped_ingest_token(uid, jti=jti)

    return _format_bridge_config_response(token, meta, api_base_url)


async def rotate_bridge_token(
    db: AsyncSession,
    user_id: uuid.UUID | str,
    api_base_url: str = "",
) -> dict[str, Any]:
    """Rotate active_jti so any previously shared device token stops working immediately."""
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    record = await _get_config_record(db, uid)
    new_token, new_jti = mint_scoped_ingest_token(uid)
    now_iso = datetime.now(UTC).isoformat()

    if record is None:
        meta = {
            "active_jti": new_jti,
            "status": "ACTIVE",
            "rotated_at": now_iso,
            "ingest_count": 0,
            "last_ingest_at": None,
            "last_app": None,
        }
        await db.execute(
            pg_insert(PaymentWebhookEvent)
            .values(
                id=uuid.uuid4(),
                event_id=_config_event_id(uid),
                event_type="upi_bridge_config",
                payload=json.dumps(meta),
                status="ACTIVE",
            )
            .on_conflict_do_update(
                index_elements=["event_id"],
                set_={"payload": json.dumps(meta), "status": "ACTIVE"},
            )
        )
    else:
        meta = json.loads(record.payload or "{}")
        meta["active_jti"] = new_jti
        meta["status"] = "ACTIVE"
        meta["rotated_at"] = now_iso
        record.payload = json.dumps(meta)
        record.status = "ACTIVE"

    await db.commit()
    return _format_bridge_config_response(new_token, meta, api_base_url)


async def verify_bridge_token(db: AsyncSession, token: str) -> uuid.UUID | None:
    """Validate HMAC signature and confirm the token's jti is still active in DB."""
    parsed = verify_scoped_ingest_token_signature(token)
    if parsed is None:
        return None
    uid, token_jti = parsed

    record = await _get_config_record(db, uid)
    if record is None or record.status != "ACTIVE":
        return None

    meta = json.loads(record.payload or "{}")
    active_jti = str(meta.get("active_jti") or "")
    if not active_jti or not hmac.compare_digest(active_jti, token_jti):
        return None
    return uid


async def ingest_upi_bridge_event(
    db: AsyncSession,
    user_id: uuid.UUID | str,
    *,
    message: str = "",
    title: str = "",
    app_package: str = "",
    source_channel: str = "android_notification",
    txn_id: str | None = None,
    timestamp: datetime | None = None,
    amount: float | None = None,
    direction: str | None = None,
    counterparty: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
) -> dict[str, Any]:
    """
    Thin optional connector entrypoint: normalizes, scrubs, persists idempotently
    into `BankTransaction` and `UnifiedTransaction`, and publishes an SSE update.
    """
    uid = uuid.UUID(str(user_id)) if not isinstance(user_id, uuid.UUID) else user_id
    parsed = parse_upi_alert_payload(
        message=message,
        title=title,
        app_package=app_package,
        source_channel=source_channel,
        txn_id=txn_id,
        timestamp=timestamp,
        amount=amount,
        direction=direction,
        counterparty=counterparty,
        category=category,
        subcategory=subcategory,
    )
    if not parsed["accepted"]:
        return {
            "status": "ignored",
            "reason": parsed["reason"],
            "imported_count": 0,
        }

    txn = parsed["transaction"]
    source_tag = f"upi_bridge:{source_channel[:30]}"
    await import_statement_transactions(db=db, user_id=uid, parsed_rows=[txn], source=source_tag)

    # Update bridge telemetry counters cleanly without storing raw payload secrets
    record = await _get_config_record(db, uid)
    if record is not None:
        meta = json.loads(record.payload or "{}")
        meta["ingest_count"] = int(meta.get("ingest_count") or 0) + 1
        meta["last_ingest_at"] = datetime.now(UTC).isoformat()
        meta["last_app"] = txn["app"]
        record.payload = json.dumps(meta)
        await db.commit()

    event_type = "bank.credit.received" if txn["type"] == "CREDIT" else "bank.debit.recorded"
    event_data = {
        "txn_id": txn["txn_id"],
        "date": txn["date"],
        "timestamp": txn["timestamp"].isoformat(),
        "amount": txn["amount"],
        "type": txn["type"],
        "mode": txn["mode"],
        "app": txn["app"],
        "vpa": txn["vpa"],
        "counterparty": txn["counterparty"],
        "category": txn["category"],
        "canonical_category": txn.get("canonical_category", "Other"),
        "subcategory": txn.get("subcategory", "General"),
        "masked_acc": txn["masked_acc"],
        "narration": txn["narration"],
        "source": source_tag,
    }
    await publish_event(
        event_type=event_type,
        data=event_data,
        customer_id=str(uid),
        event_id=f"upi_bridge_{txn['txn_id']}",
    )

    return {
        "status": "ingested",
        "imported_count": 1,
        "transaction": event_data,
    }
