from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.user import User
from app.services.auth import get_current_user
from app.services.forecasting import generate_business_ai_forecast
from app.services.ml_models import summarize_payments_made_to_others

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

