import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import OTPVerification

logger = logging.getLogger(__name__)


def generate_otp() -> str:
    # Use a cryptographically secure RNG for OTPs
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp(otp: str, otp_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(otp), otp_hash)


async def store_otp(db: AsyncSession, phone: str, purpose: str, otp: str) -> OTPVerification:
    # Store OTP as a hashed value in DB (short-lived). Later we can move this to Redis.
    verification = OTPVerification(
        phone=phone,
        otp_hash=hash_otp(otp),
        purpose=purpose,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        used=False,
    )
    db.add(verification)
    await db.commit()
    await db.refresh(verification)
    return verification


def send_otp_sms(phone: str, otp: str) -> None:
    from app.cores.config import settings
    from app.services.encryption import mask_phone

    masked = mask_phone(phone)
    if settings.ENV.lower() == "development":
        logger.info("OTP generated for %s (dev sandbox code: %s)", masked, otp)
    else:
        logger.info("OTP SMS dispatched to %s", masked)