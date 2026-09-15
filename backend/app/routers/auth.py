from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.cores.database import get_db
from app.cores.config import settings
import hashlib
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.transaction import OTPVerification
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth import (
    create_access_token,
    hash_password,
    verify_password,
    generate_refresh_token,
    store_refresh_token,
    verify_and_rotate_refresh_token,
)
from app.services.otp import generate_otp, send_otp_sms, store_otp, verify_otp

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # create refresh token and set as httpOnly cookie
    access = create_access_token(str(user.id))
    raw_refresh = generate_refresh_token()
    await store_refresh_token(db, str(user.id), raw_refresh)
    res = TokenResponse(access_token=access)
    response = Response(content=res.json(), media_type="application/json")
    secure = settings.ENV.lower() != "development"
    response.set_cookie(
        key="refresh",
        value=raw_refresh,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth/refresh",
        max_age=60 * 60 * 24 * 30,
    )
    return response


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access = create_access_token(str(user.id))
    raw_refresh = generate_refresh_token()
    await store_refresh_token(db, str(user.id), raw_refresh)
    res = TokenResponse(access_token=access)
    response = Response(content=res.json(), media_type="application/json")
    secure = settings.ENV.lower() != "development"
    response.set_cookie(
        key="refresh",
        value=raw_refresh,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth/refresh",
        max_age=60 * 60 * 24 * 30,
    )
    return response


@router.post("/otp/send")
async def send_otp(phone: str, purpose: str = "TRANSACTION", db: AsyncSession = Depends(get_db)):
    otp = generate_otp()
    await store_otp(db, phone, purpose, otp)
    send_otp_sms(phone, otp)
    return {"message": "OTP sent"}



@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, db: AsyncSession = Depends(get_db)):
    # read refresh token from httpOnly cookie
    raw = request.cookies.get("refresh")
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    data = await verify_and_rotate_refresh_token(db, raw)
    if not data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    access = create_access_token(data["user_id"])
    # set rotated refresh token cookie
    response = TokenResponse(access_token=access)
    resp = Response(content=response.json(), media_type="application/json")
    secure = settings.ENV.lower() != "development"
    resp.set_cookie(
        key="refresh",
        value=data["raw"],
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/api/v1/auth/refresh",
        max_age=60 * 60 * 24 * 30,
    )
    return resp


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_db)):
    raw = request.cookies.get("refresh")
    if raw:
        # mark token revoked if present
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        token_row = result.scalar_one_or_none()
        if token_row:
            token_row.revoked = True
            await db.commit()
    # clear cookie
    res = Response(content={"message": "logged out"})
    res.delete_cookie("refresh", path="/api/v1/auth/refresh")
    return res


@router.post("/otp/verify")
async def verify_otp_endpoint(phone: str, otp: str, purpose: str = "TRANSACTION", db: AsyncSession = Depends(get_db)):
    # Find the most recent unused OTP for this phone+purpose that hasn't expired
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(OTPVerification)
        .where(
            OTPVerification.phone == phone,
            OTPVerification.purpose == purpose,
            OTPVerification.used == False,
            OTPVerification.expires_at > now,
        )
        .order_by(OTPVerification.created_at.desc())
    )
    verification = result.scalars().first()
    if not verification:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")

    if verify_otp(otp, verification.otp_hash):
        verification.used = True
        await db.commit()
        return {"verified": True, "message": "OTP verified"}

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP")