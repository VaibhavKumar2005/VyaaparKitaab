from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.user import User
from app.services.auth import get_current_user
from app.services.forecasting import generate_business_ai_forecast
from app.services.ml_models import summarize_payments_made_to_others
from app.services.nl_assistant import answer_financial_question
from app.services.timeseries import build_cashflow_timeseries

router = APIRouter(prefix="/ai", tags=["ai-forecasting"])


@router.get("/forecast")
async def get_ai_forecast(
    lookback_days: int = Query(default=30, ge=7, le=90),
    horizon_days: int = Query(default=7, ge=3, le=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Returns AI/ML demand forecasts, SKU days-to-stockout predictions,
    chronological validation metrics (MAE / RMSE for SMA-7, Holt-Linear, RidgeRegression,
    and RandomForestRegressor), and 7-day revenue / cash-flow projections.
    """
    return await generate_business_ai_forecast(
        db=db,
        user_id=user.id,
        lookback_days=lookback_days,
        horizon_days=horizon_days,
    )


@router.get("/payments-summary")
async def get_ai_outgoing_payments_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    ML-powered summary of all payments made by the user to others, using pandas + scikit-learn
    (KMeans payee clustering, Ridge/RandomForest outflow forecasting, IsolationForest anomaly detection).
    """
    return await summarize_payments_made_to_others(db=db, user=user)


class AssistantQueryRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)


@router.post("/assistant")
async def query_financial_assistant(
    payload: AssistantQueryRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Data-grounded natural language assistant answering spending, discount, store revenue,
    and forecast queries directly from `unified_transactions` and ML models.
    """
    return await answer_financial_question(db=db, user=user, question=payload.question)


@router.get("/cashflow-timeseries")
async def get_cashflow_timeseries(
    lookback_days: int = Query(default=30, ge=7, le=180),
    horizon_days: int = Query(default=14, ge=3, le=30),
    granularity: str = Query(default="daily", pattern="^(daily|weekly)$"),
    view: str = Query(default="all", pattern="^(all|customer|store)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Unified chronological time-series & multi-model cashflow forecast built directly
    over streamlined SMS/UPI alerts, Razorpay settlements, statements, OCR bills,
    and store invoices (with 80% prediction bands, weekday seasonality & anomaly flags).
    """
    return await build_cashflow_timeseries(
        db=db,
        user=user,
        lookback_days=lookback_days,
        horizon_days=horizon_days,
        granularity=granularity,
        view=view,
    )

