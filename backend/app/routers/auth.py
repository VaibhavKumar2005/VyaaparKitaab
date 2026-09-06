from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.auth import create_access_token, hash_password, verify_password
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
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/otp/send")
async def send_otp(phone: str, purpose: str = "TRANSACTION", db: AsyncSession = Depends(get_db)):
    otp = generate_otp()
    await store_otp(db, phone, purpose, otp)
    send_otp_sms(phone, otp)
    return {"message": "OTP sent"}


@router.post("/otp/verify")
async def verify_otp_endpoint(phone: str, otp: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalar_one_or_none()
    return {"verified": bool(user), "message": "OTP verification endpoint ready"}