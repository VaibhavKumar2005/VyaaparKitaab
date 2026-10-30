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
    SECRET_KEY: str = Field(default="change-me-to-a-secure-random-key")
    ENCRYPTION_KEY: str = Field(default="")
    ENV: str = Field(default="development")
    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*"]
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

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value):
        if value in (None, ""):
            return ["*"]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    def validate_production_security(self) -> None:
        if self.ENV.lower() == "production" and self.SECRET_KEY in (
            "",
            "change-me-to-a-secure-random-key",
            "ci-secret",
        ):
            raise ValueError("CRITICAL: SECRET_KEY must be set to a strong secret in production")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.validate_production_security()
    return s


settings = get_settings()