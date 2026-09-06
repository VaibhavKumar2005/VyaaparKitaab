from functools import lru_cache

from pydantic import field_validator
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = Field(...)
    SECRET_KEY: str = Field(default="change-me")
    ENV: str = Field(default="development")
    ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)

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