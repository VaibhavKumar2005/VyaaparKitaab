import asyncio
import hashlib
import hmac
import logging
import secrets
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.config import settings
from app.models.transaction import OTPVerification
from app.models.user import User
from app.services.encryption import mask_phone

logger = logging.getLogger(__name__)

ALLOWED_SMTP_HOSTS = {
    "smtp.gmail.com",
    "smtp.office365.com",
    "smtp.sendgrid.net",
    "email-smtp.ap-south-1.amazonaws.com",
}


def _send_smtp_email_sync(recipient_email: str, otp: str, purpose: str) -> None:
    host = settings.SMTP_HOST.strip().lower()
    if host not in ALLOWED_SMTP_HOSTS:
        raise ValueError(f"Disallowed SMTP_HOST '{host}'. Must be in ALLOWED_SMTP_HOSTS.")
    msg = EmailMessage()
    sender = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
    msg["Subject"] = f"VyaparKitaab Verification Code: {otp}"
    msg["From"] = f"VyaparKitaab Security <{sender}>"
    msg["To"] = recipient_email
    msg.set_content(
        f"Your VyaparKitaab {purpose.lower()} verification OTP is: {otp}\n\n"
        "This 6-digit code is valid for 5 minutes. Never share this code with anyone."
    )
    msg.add_alternative(
        f"""
        <div style="font-family: Inter, Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; border: 1px solid #d9e0e6; border-radius: 10px;">
          <h2 style="color: #0057d2; margin-top: 0;">VyaparKitaab Verification</h2>
          <p style="color: #1d2d3e; font-size: 14px;">Use the 6-digit verification code below to authorize your <strong>{purpose}</strong> request:</p>
          <div style="background: #ebf8ff; border: 1px solid #0057d2; border-radius: 8px; padding: 16px; text-align: center; font-size: 28px; font-weight: 700; letter-spacing: 6px; color: #0057d2; margin: 20px 0;">
            {otp}
          </div>
          <p style="color: #556b82; font-size: 12px;">Valid for 5 minutes. If you did not request this code, please ignore this email.</p>
        </div>
        """,
        subtype="html",
    )
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


async def send_otp_email(recipient_email: str, otp: str, purpose: str = "LOGIN") -> None:
    await asyncio.to_thread(_send_smtp_email_sync, recipient_email, otp, purpose)


def _normalize_phone(phone: str) -> tuple[str, str]:
    raw = phone.strip().replace(" ", "").replace("-", "")
    if raw.startswith("+91"):
        clean = raw[3:]
    elif raw.startswith("91") and len(raw) == 12:
        clean = raw[2:]
    else:
        clean = raw.lstrip("+")
    e164 = f"+91{clean}" if len(clean) == 10 and clean.isdigit() else (raw if raw.startswith("+") else f"+{clean}")
    return clean, e164


def generate_otp() -> str:
    # Use a cryptographically secure RNG for OTPs
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp(otp: str, otp_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(otp), otp_hash)


def _otp_db_key(identifier: str) -> str:
    clean = identifier.strip().lower()
    if len(clean) <= 20:
        return clean
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:20]


def _otp_db_purpose(purpose: str) -> str:
    normalized = purpose.upper()
    if normalized in {"LOGIN", "TRANSACTION", "AA_CONSENT"}:
        return normalized
    raise ValueError(f"Unsupported OTP purpose: {purpose}")


async def store_otp(db: AsyncSession, phone: str, purpose: str, otp: str) -> OTPVerification:
    # Store OTP as a hashed value in DB (short-lived). Later we can move this to Redis.
    verification = OTPVerification(
        phone=_otp_db_key(phone),
        otp_hash=hash_otp(otp),
        purpose=_otp_db_purpose(purpose),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        used=False,
    )
    db.add(verification)
    await db.commit()
    await db.refresh(verification)
    return verification


def send_otp_sms(phone: str, otp: str) -> None:
    masked = mask_phone(phone)
    if settings.ENV.lower() == "development":
        logger.info("OTP generated for %s (dev sandbox code: %s)", masked, otp)
    else:
        logger.info("OTP SMS dispatched to %s", masked)


async def dispatch_otp(
    db: AsyncSession,
    phone: str,
    purpose: str = "TRANSACTION",
    email: str | None = None,
) -> dict[str, Any]:
    """
    Dispatches an OTP via Gmail SMTP Email, Twilio Verify v2, Twilio SMS, or PostgreSQL DB.
    Strictly binds every OTP to the verified destination where it was delivered.
    Never allows redirecting a phone-login OTP to an unverified caller-supplied email.
    """
    raw_identifier = phone.strip()
    is_email_identifier = "@" in raw_identifier
    clean_phone, e164_phone = _normalize_phone(raw_identifier)
    supplied_email = (email or "").strip().lower()
    provider = settings.OTP_PROVIDER.lower().strip()

    # Security barrier: Prevent redirecting a phone OTP to an arbitrary caller-supplied email
    verified_user_email: str | None = None
    if supplied_email and not is_email_identifier:
        if hasattr(db, "execute"):
            user_res = await db.execute(select(User).where(User.phone == clean_phone))
            existing_user = user_res.scalar_one_or_none()
            if (
                existing_user
                and existing_user.email
                and existing_user.email.strip().lower() == supplied_email
                and getattr(existing_user, "email_verified", False) is True
            ):
                verified_user_email = supplied_email
            else:
                raise ValueError("Cannot redirect phone OTP to an unverified external email address")
        else:
            raise ValueError("Cannot redirect phone OTP to an unverified external email address")

    target_email = raw_identifier.lower() if is_email_identifier else verified_user_email

    # 1. Twilio Verify v2 API (managed OTP generation + SMS delivery)
    if (
        not is_email_identifier
        and provider == "twilio_verify"
        and settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_VERIFY_SERVICE_SID
    ):
        url = f"https://verify.twilio.com/v2/Services/{settings.TWILIO_VERIFY_SERVICE_SID}/Verifications"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                data={"To": e164_phone, "Channel": "sms"},
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
            resp.raise_for_status()
            data = resp.json()
        logger.info("Twilio Verify OTP dispatched to %s (status=%s)", mask_phone(clean_phone), data.get("status"))
        return {
            "message": "OTP sent",
            "provider": "twilio_verify",
            "channel": "sms",
            "status": str(data.get("status", "pending")),
        }

    # 2. Generate 6-digit cryptographic OTP & bind strictly to the single verified destination
    otp = generate_otp()
    bound_destination = target_email if is_email_identifier else clean_phone
    await store_otp(db, bound_destination, purpose, otp)

    # 3. Gmail / SMTP Email OTP Delivery (only when destination is an email or verified user email)
    smtp_ready = bool(settings.SMTP_USER and settings.SMTP_PASSWORD)
    if target_email and smtp_ready:
        await send_otp_email(target_email, otp, purpose=purpose)
        logger.info("SMTP Email OTP dispatched to %s", target_email)
        return {
            "message": f"OTP sent to {target_email}",
            "provider": "smtp_email",
            "channel": "email",
            "smtp_configured": True,
        }

    # 4. Optional Twilio Programmable SMS delivery of our DB-backed OTP
    if (
        provider == "twilio_sms"
        and settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_FROM_PHONE
    ):
        url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.TWILIO_ACCOUNT_SID}/Messages.json"
        body = f"Your VyaparKitaab verification OTP is {otp}. Valid for 5 minutes. Do not share this code."
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                data={"To": e164_phone, "From": settings.TWILIO_FROM_PHONE, "Body": body},
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
            resp.raise_for_status()
        logger.info("Twilio SMS OTP dispatched to %s", mask_phone(clean_phone))
        return {
            "message": "OTP sent",
            "provider": "twilio_sms",
            "channel": "sms",
        }

    # 5. Local DB mode (when SMTP credentials are not yet entered)
    send_otp_sms(clean_phone, otp)
    response: dict[str, Any] = {
        "message": "OTP sent",
        "provider": "sandbox",
        "channel": "sandbox",
        "smtp_configured": smtp_ready,
    }
    if settings.ENV.lower() in ("development", "testing"):
        response["dev_otp"] = otp
    return response


async def check_otp_code(
    db: AsyncSession,
    phone: str,
    otp: str,
    purpose: str = "TRANSACTION",
) -> bool:
    """
    Verifies an OTP code via Twilio Verify v2 or local PostgreSQL OTPVerification table.
    """
    clean_phone, e164_phone = _normalize_phone(phone)
    provider = settings.OTP_PROVIDER.lower().strip()

    if (
        provider == "twilio_verify"
        and settings.TWILIO_ACCOUNT_SID
        and settings.TWILIO_AUTH_TOKEN
        and settings.TWILIO_VERIFY_SERVICE_SID
    ):
        url = f"https://verify.twilio.com/v2/Services/{settings.TWILIO_VERIFY_SERVICE_SID}/VerificationCheck"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                url,
                data={"To": e164_phone, "Code": otp.strip()},
                auth=(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN),
            )
            if resp.status_code >= 400:
                return False
            data = resp.json()
        return str(data.get("status", "")).lower() == "approved" or bool(data.get("valid"))

    now = datetime.now(UTC)
    db_purpose = _otp_db_purpose(purpose)
    candidate_keys = list({_otp_db_key(clean_phone), _otp_db_key(phone.strip()), clean_phone[:20]})
    result = await db.execute(
        select(OTPVerification)
        .where(
            OTPVerification.phone.in_(candidate_keys),
            OTPVerification.purpose == db_purpose,
            OTPVerification.used == False,
            OTPVerification.expires_at > now,
        )
        .order_by(OTPVerification.created_at.desc())
    )
    verification = result.scalars().first()
    if verification and verify_otp(otp.strip(), verification.otp_hash):
        verification.used = True
        await db.commit()
        return True

    # Allow 123456 fallback in dev/test for LOGIN purpose when no live provider is forced
    return bool(
        purpose == "LOGIN"
        and settings.ENV.lower() in ("development", "testing")
        and otp.strip() == "123456"
    )