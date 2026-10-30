from app.routers.ai_insights import router as ai_router
from app.routers.auth import router as auth_router
from app.routers.banking import router as banking_router
from app.routers.business import router as business_router
from app.routers.health import router as health_router
from app.routers.payments import router as payments_router
from app.routers.purchases import router as purchases_router
from app.routers.streams import router as streams_router
from app.routers.transactions import router as transactions_router

__all__ = [
    "ai_router",
    "auth_router",
    "banking_router",
    "business_router",
    "health_router",
    "payments_router",
    "purchases_router",
    "streams_router",
    "transactions_router",
]
