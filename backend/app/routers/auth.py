from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
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

    allowed_roles = {"STORE_OWNER", "CUSTOMER", "STAFF"}
    role = payload.role if payload.role in allowed_roles else "STORE_OWNER"

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    # create refresh token and set as httpOnly cookie
    access = create_access_token(str(user.id), user.role)
    raw_refresh = generate_refresh_token()
    await store_refresh_token(db, str(user.id), raw_refresh)
    res = TokenResponse(access_token=access)
    response = Response(content=res.model_dump_json(), media_type="application/json")
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
    access = create_access_token(str(user.id), user.role)
    raw_refresh = generate_refresh_token()
    await store_refresh_token(db, str(user.id), raw_refresh)
    res = TokenResponse(access_token=access)
    response = Response(content=res.model_dump_json(), media_type="application/json")
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
    clean_phone = phone.strip().replace(" ", "").replace("+91", "")
    otp = generate_otp()
    await store_otp(db, clean_phone, purpose, otp)
    send_otp_sms(clean_phone, otp)
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
    user_result = await db.execute(select(User).where(User.id == data["user_id"]))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    access = create_access_token(data["user_id"], user.role)
    # set rotated refresh token cookie
    response = TokenResponse(access_token=access)
    resp = Response(content=response.model_dump_json(), media_type="application/json")
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
    res = JSONResponse(content={"message": "logged out"})
    res.delete_cookie("refresh", path="/api/v1/auth/refresh")
    return res


@router.post("/otp/verify")
async def verify_otp_endpoint(phone: str, otp: str, purpose: str = "TRANSACTION", db: AsyncSession = Depends(get_db)):
    clean_phone = phone.strip().replace(" ", "").replace("+91", "")
    # Find the most recent unused OTP for this phone+purpose that hasn't expired
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(OTPVerification)
        .where(
            OTPVerification.phone.in_([clean_phone, phone.strip()]),
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


class CustomerOtpLoginRequest(BaseModel):
    phone: str
    otp: str


class BusinessKycRequest(BaseModel):
    gstin: str
    bank_account: str
    ifsc: str


@router.post("/customer/otp-login", response_model=TokenResponse)
async def customer_otp_login(payload: CustomerOtpLoginRequest, db: AsyncSession = Depends(get_db)):
    """Universal Indian consumer frictionless login: Mobile number + OTP."""
    import uuid

    clean_phone = payload.phone.strip().replace(" ", "").replace("+91", "")
    if not clean_phone.isdigit() or len(clean_phone) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number format")

    is_sandbox_otp_allowed = settings.ENV.lower() in ("development", "testing") and payload.otp == "123456"
    if not is_sandbox_otp_allowed:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(OTPVerification)
            .where(
                OTPVerification.phone == clean_phone,
                OTPVerification.purpose == "LOGIN",
                OTPVerification.used == False,
                OTPVerification.expires_at > now,
            )
            .order_by(OTPVerification.created_at.desc())
        )
        verification = result.scalars().first()
        if not verification or not verify_otp(payload.otp, verification.otp_hash):
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")
        verification.used = True

    # Find or auto-register customer account for this phone
    res = await db.execute(select(User).where(User.phone == clean_phone))
    user = res.scalar_one_or_none()
    if not user:
        user = User(
            id=uuid.uuid4(),
            email=f"{clean_phone}@customer.vyaapar.local",
            hashed_password=hash_password(uuid.uuid4().hex),
            full_name=f"Customer ({clean_phone[-4:]})",
            phone=clean_phone,
            role="CUSTOMER",
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    access = create_access_token(str(user.id), user.role)
    raw_refresh = generate_refresh_token()
    await store_refresh_token(db, str(user.id), raw_refresh)
    res = TokenResponse(access_token=access)
    response = Response(content=res.model_dump_json(), media_type="application/json")
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


@router.post("/business/verify-kyc")
async def verify_business_kyc(
    payload: BusinessKycRequest,
    db: AsyncSession = Depends(get_db),
):
    """Verify GSTIN and Settlement Bank Account for Merchant Store Owner."""
    from app.services.kyc import verify_gstin, verify_bank_account
    from app.models.business import Business

    gst_result = verify_gstin(payload.gstin)
    if not gst_result.get("valid"):
        raise HTTPException(status_code=400, detail=gst_result.get("error"))

    bank_result = verify_bank_account(payload.bank_account, payload.ifsc)
    if not bank_result.get("valid"):
        raise HTTPException(status_code=400, detail=bank_result.get("error"))

    return {
        "status": "VERIFIED",
        "gst_details": gst_result,
        "bank_settlement": bank_result,
        "message": "Business KYC successfully verified.",
    }