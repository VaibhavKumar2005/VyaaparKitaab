from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.cores.config import settings
from app.cores.database import Base, engine
from app.cores.exceptions import register_exception_handlers
import app.models  # noqa: F401 - ensures model metadata is registered before create_all
from app.routers.auth import router as auth_router
from app.routers.business import router as business_router
from app.routers.health import router as health_router
from app.routers.transactions import router as transactions_router

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.ENV.lower() == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="VyaparKitaab API", version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "img-src 'self' data: blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "connect-src 'self'"
    )
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"status": "backend running"}


app.include_router(health_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(business_router, prefix="/api/v1")
app.include_router(transactions_router, prefix="/api/v1")