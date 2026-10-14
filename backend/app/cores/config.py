from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic import Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = Field(default="postgresql://postgres@localhost:5432/vyaapardb")
    SECRET_KEY: str = Field(default="change-me-to-a-secure-random-key")
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

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value):
        if value in (None, ""):
            return ["*"]
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()