from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = Field(default="postgresql://postgres@localhost:5432/vyaapardb")
    DATABASE_DIRECT_URL: str = Field(default="")
    DB_SSL_VERIFY: bool = Field(default=True)
    EVENT_BUS_BACKEND: str = Field(default="memory")  # "memory" or "postgres"
    EVENT_BUS_CHANNEL: str = Field(default="vk_events")
    SECRET_KEY: str = Field(default="change-me-to-a-secure-random-key")
    ENCRYPTION_KEY: str = Field(default="")
    ENV: str = Field(default="development")
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
        ]
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)

    # Payment Gateway Configuration (e.g. Razorpay, Cashfree, PhonePe)
    PAYMENT_GATEWAY: str = Field(default="sandbox")  # "sandbox" or "razorpay"
    PAYMENT_KEY_ID: str = Field(default="")
    PAYMENT_KEY_SECRET: str = Field(default="")
    PAYMENT_WEBHOOK_SECRET: str = Field(default="")

    # Bank Inflows & Account Aggregator Data Provider ("mock" or "setu_aa")
    BANK_DATA_PROVIDER: str = Field(default="mock")
    SETU_AA_BASE_URL: str = Field(default="https://fiu-sandbox.setu.co/v2")
    SETU_AA_CLIENT_ID: str = Field(default="")
    SETU_AA_CLIENT_SECRET: str = Field(default="")
    SETU_AA_PRODUCT_INSTANCE_ID: str = Field(default="")
    SETU_AA_REDIRECT_URL: str = Field(default="http://localhost:5173/app/dashboard")
    SETU_AA_WEBHOOK_SECRET: str = Field(default="")

    # OTP & SMS / Email Verification Provider ("smtp_email", "twilio_verify", "twilio_sms", or "sandbox")
    OTP_PROVIDER: str = Field(default="smtp_email")
    TWILIO_ACCOUNT_SID: str = Field(default="")
    TWILIO_AUTH_TOKEN: str = Field(default="")
    TWILIO_VERIFY_SERVICE_SID: str = Field(default="")
    TWILIO_FROM_PHONE: str = Field(default="")

    # Gmail / SMTP Email OTP Configuration
    SMTP_HOST: str = Field(default="smtp.gmail.com")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    SMTP_FROM_EMAIL: str = Field(default="")

    # OCR & Handwritten Hindi Receipt Configuration
    # Offline Tesseract uses "hin+eng" (when tesseract-ocr-hin is installed).
    # Optional GEMINI_API_KEY enables Gemini Vision for handwritten Hindi kacha parchas.
    OCR_DEFAULT_LANG: str = Field(default="auto")
    GEMINI_API_KEY: str = Field(default="")
    OCR_GEMINI_MODEL: str = Field(default="gemini-2.5-flash")

    # Optional Production Error Monitoring (Sentry Cloud or self-hosted GlitchTip DSN)
    SENTRY_DSN: str = Field(default="")
    SENTRY_TRACES_SAMPLE_RATE: float = Field(default=0.1)

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value):
        if value in (None, ""):
            return ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    def validate_production_security(self) -> None:
        if self.ENV.lower() != "production":
            return
        weak_keys = {
            "",
            "change-me-to-a-secure-random-key",
            "generate-a-strong-secret-key-at-least-32-chars",
            "ci-secret",
        }
        if self.SECRET_KEY.strip() in weak_keys or len(self.SECRET_KEY.strip()) < 32:
            raise ValueError("CRITICAL: SECRET_KEY must be a strong secret (>= 32 chars) in production")
        if not self.ENCRYPTION_KEY.strip() or len(self.ENCRYPTION_KEY.strip()) < 32:
            raise ValueError("CRITICAL: ENCRYPTION_KEY (>= 32 chars) must be set explicitly in production")
        if "*" in self.ALLOWED_ORIGINS:
            raise ValueError("CRITICAL: Wildcard '*' in ALLOWED_ORIGINS is forbidden in production")
        if self.OTP_PROVIDER.strip().lower() == "sandbox":
            raise ValueError("CRITICAL: OTP_PROVIDER='sandbox' is forbidden in production")
        if self.PAYMENT_GATEWAY.strip().lower() == "razorpay" and not (
            self.PAYMENT_KEY_ID.strip() and self.PAYMENT_KEY_SECRET.strip() and self.PAYMENT_WEBHOOK_SECRET.strip()
        ):
            raise ValueError(
                "CRITICAL: PAYMENT_KEY_ID, PAYMENT_KEY_SECRET, and PAYMENT_WEBHOOK_SECRET are required for Razorpay in production"
            )
        if self.BANK_DATA_PROVIDER.strip().lower() == "setu_aa" and not self.SETU_AA_WEBHOOK_SECRET.strip():
            raise ValueError("CRITICAL: SETU_AA_WEBHOOK_SECRET is required when BANK_DATA_PROVIDER='setu_aa' in production")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.validate_production_security()
    return s


settings = get_settings()