import hashlib
import hmac
import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import OTPVerification

logger = logging.getLogger(__name__)


def generate_otp() -> str:
    return f"{random.randint(0, 999999):06d}"


def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp(otp: str, otp_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(otp), otp_hash)


async def store_otp(db: AsyncSession, phone: str, purpose: str, otp: str) -> OTPVerification:
    verification = OTPVerification(
        phone=phone,
        otp_hash=hash_otp(otp),
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        used=False,
    )
    db.add(verification)
    await db.commit()
    await db.refresh(verification)
    return verification


def send_otp_sms(phone: str, otp: str) -> None:
    logger.info("OTP %s sent to %s (stub; integrate Fast2SMS/Twilio later)", otp, phone)