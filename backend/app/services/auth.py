from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import secrets
import hashlib
import hmac
from app.models.refresh_token import RefreshToken

from app.cores.config import settings
from app.cores.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_refresh_token(raw_length: int = 64) -> str:
    # high-entropy opaque token
    return secrets.token_urlsafe(raw_length)


async def store_refresh_token(db: AsyncSession, user_id: str, raw_token: str, days: int = 30) -> RefreshToken:
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    refresh = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(refresh)
    await db.commit()
    await db.refresh(refresh)
    return refresh


async def verify_and_rotate_refresh_token(db: AsyncSession, raw_token: str, days: int = 30):
    token_hash = _hash_token(raw_token)
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    token_row = result.scalar_one_or_none()
    if not token_row:
        return None
    # constant-time comparison
    if not hmac.compare_digest(token_row.token_hash, token_hash):
        return None
    if token_row.revoked:
        return None
    if token_row.expires_at < datetime.now(timezone.utc):
        return None
    # rotate: revoke (or delete) old token and create a new one
    token_row.revoked = True
    await db.commit()
    new_raw = generate_refresh_token()
    new_row = await store_refresh_token(db, str(token_row.user_id), new_raw, days=days)
    return {"user_id": str(token_row.user_id), "raw": new_raw}


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        subject = payload.get("sub")
        if not subject:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == subject))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user