import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.config import settings
from app.cores.database import get_db
from app.cores.rate_limit import check_rate_limit
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    store_refresh_token,
    verify_and_rotate_refresh_token,
    verify_password,
)
from app.services.otp import check_otp_code, dispatch_otp

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
    check_rate_limit(f"login:{payload.email.lower()}", max_requests=10, window_seconds=60)
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
async def send_otp(
    phone: str,
    purpose: str = "TRANSACTION",
    email: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    raw_identifier = phone.strip()
    clean_phone = raw_identifier if "@" in raw_identifier else raw_identifier.replace(" ", "").replace("+91", "")
    check_rate_limit(f"otp_send:{clean_phone}", max_requests=5, window_seconds=60)
    try:
        return await dispatch_otp(db, clean_phone, purpose, email=email)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send OTP via SMTP/Gateway: {exc}",
        ) from exc


@router.get("/otp/status")
async def get_otp_status():
    return {
        "provider": settings.OTP_PROVIDER,
        "smtp_configured": bool(settings.SMTP_USER and settings.SMTP_PASSWORD),
    }



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
    raw_identifier = phone.strip()
    clean_phone = raw_identifier.lower() if "@" in raw_identifier else raw_identifier.replace(" ", "").replace("+91", "")
    check_rate_limit(f"otp_verify:{clean_phone}", max_requests=10, window_seconds=60)
    is_valid = await check_otp_code(db, clean_phone, otp, purpose)
    if is_valid:
        if "@" in clean_phone:
            user_res = await db.execute(select(User).where(User.email == clean_phone))
            u = user_res.scalar_one_or_none()
            if u:
                u.email_verified = True
                await db.commit()
        else:
            user_res = await db.execute(select(User).where(User.phone == clean_phone))
            u = user_res.scalar_one_or_none()
            if u:
                u.phone_verified = True
                await db.commit()
        return {"verified": True, "message": "OTP verified"}
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OTP")


class CustomerOtpLoginRequest(BaseModel):
    phone: str
    otp: str


class BusinessKycRequest(BaseModel):
    gstin: str
    bank_account: str
    ifsc: str


@router.post("/customer/otp-login", response_model=TokenResponse)
async def customer_otp_login(payload: CustomerOtpLoginRequest, db: AsyncSession = Depends(get_db)):
    """Universal Indian consumer frictionless login: Verified Mobile number or Email + OTP."""
    import uuid

    raw_identifier = payload.phone.strip()
    is_email_login = "@" in raw_identifier
    if is_email_login:
        clean_identifier = raw_identifier.lower()
    else:
        clean_identifier = raw_identifier.replace(" ", "").replace("+91", "")
        if not clean_identifier.isdigit() or len(clean_identifier) < 10:
            raise HTTPException(status_code=400, detail="Invalid phone number format")

    is_valid = await check_otp_code(db, clean_identifier, payload.otp, purpose="LOGIN")
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    if is_email_login:
        res = await db.execute(select(User).where(User.email == clean_identifier))
        user = res.scalar_one_or_none()
        if not user:
            user = User(
                id=uuid.uuid4(),
                email=clean_identifier,
                hashed_password=hash_password(uuid.uuid4().hex),
                full_name=f"Customer ({clean_identifier.split('@')[0]})",
                role="CUSTOMER",
                is_active=True,
                email_verified=True,
            )
            db.add(user)
        else:
            user.email_verified = True
        await db.commit()
        await db.refresh(user)
    else:
        res = await db.execute(select(User).where(User.phone == clean_identifier))
        user = res.scalar_one_or_none()
        if not user:
            user = User(
                id=uuid.uuid4(),
                email=f"{clean_identifier}@customer.vyaapar.local",
                hashed_password=hash_password(uuid.uuid4().hex),
                full_name=f"Customer ({clean_identifier[-4:]})",
                phone=clean_identifier,
                role="CUSTOMER",
                is_active=True,
                phone_verified=True,
            )
            db.add(user)
        else:
            user.phone_verified = True
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
    from app.services.kyc import verify_bank_account, verify_gstin

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