import ssl
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.cores.config import settings


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _should_use_ssl(url: str) -> bool:
    hostname = urlsplit(url).hostname
    return hostname not in {"localhost", "127.0.0.1", "db"}


DATABASE_URL = _normalize_database_url(settings.DATABASE_URL)

engine_kwargs = {"echo": False, "future": True}
if _should_use_ssl(DATABASE_URL):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    engine_kwargs["connect_args"] = {"ssl": ssl_context}

engine = create_async_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with SessionLocal() as session:
        yield session