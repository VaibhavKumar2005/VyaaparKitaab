from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.business import Business, Product
from app.models.transaction import Invoice
from app.services.ml_models import train_and_compare_sklearn_forecasters


def _compute_mae_rmse(actual: list[float], predicted: list[float]) -> tuple[float, float]:
    if not actual or len(actual) != len(predicted):
        return 0.0, 0.0
    n = len(actual)
    abs_errors = [abs(a - p) for a, p in zip(actual, predicted, strict=False)]
    sq_errors = [(a - p) ** 2 for a, p in zip(actual, predicted, strict=False)]
    mae = sum(abs_errors) / n
    rmse = math.sqrt(sum(sq_errors) / n)
    return round(mae, 2), round(rmse, 2)


def _sma_forecast(train_series: list[float], horizon: int, window: int = 7) -> list[float]:
    """Simple Moving Average baseline forecaster."""
    if not train_series:
        return [0.0] * horizon
    history = list(train_series)
    preds: list[float] = []
    for _ in range(horizon):
        w = history[-window:] if len(history) >= window else history
        val = max(0.0, sum(w) / len(w))
        preds.append(round(val, 2))
        history.append(val)
    return preds


def _holt_linear_forecast(
    train_series: list[float],
    horizon: int,
    alpha: float = 0.35,
    beta: float = 0.15,
) -> list[float]:
    """
    Holt's Two-Parameter Double Exponential Smoothing for level + trend time series.
    Handles non-stationary MSME retail demand and cash-flow series with damped clamping.
    """
    if not train_series:
        return [0.0] * horizon
    if len(train_series) == 1:
        return [round(max(0.0, train_series[0]), 2)] * horizon

    level = float(train_series[0])
    trend = float(train_series[1] - train_series[0])

    for obs in train_series[1:]:
        prev_level = level
        level = alpha * float(obs) + (1.0 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1.0 - beta) * trend

    forecasts: list[float] = []
    for step in range(1, horizon + 1):
        # Apply gentle trend damping (0.9^step) to prevent runaway extrapolation
        damped_step = sum(0.9**i for i in range(1, step + 1))
        pred = max(0.0, level + damped_step * trend)
        forecasts.append(round(pred, 2))
    return forecasts


def evaluate_and_forecast_series(
    daily_values: list[float],
    horizon: int = 7,
) -> dict[str, Any]:
    """
    Performs a chronological train/validation split (80% train / 20% validation),
    compares Naive SMA-7 vs. Holt-Linear Exponential Smoothing using MAE and RMSE,
    selects the superior model, retrains on 100% of historical data, and forecasts `horizon` days.
    """
    clean_series = [max(0.0, float(v or 0.0)) for v in daily_values]
    n = len(clean_series)
    if n < 5:
        preds = _sma_forecast(clean_series, horizon)
        return {
            "selected_model": "SMA-7",
            "models_compared": {
                "SMA-7": {"mae": 0.0, "rmse": 0.0},
                "Holt-Linear": {"mae": 0.0, "rmse": 0.0},
            },
            "forecast": preds,
        }

    val_size = max(2, round(n * 0.2))
    train = clean_series[:-val_size]
    val = clean_series[-val_size:]

    sma_val_preds = _sma_forecast(train, val_size)
    holt_val_preds = _holt_linear_forecast(train, val_size)

    sma_mae, sma_rmse = _compute_mae_rmse(val, sma_val_preds)
    holt_mae, holt_rmse = _compute_mae_rmse(val, holt_val_preds)

    sklearn_res = train_and_compare_sklearn_forecasters(clean_series, horizon=horizon)
    sk_metrics = sklearn_res["metrics"]

    if holt_rmse <= sma_rmse:
        selected = "Holt-Linear"
        final_forecast = _holt_linear_forecast(clean_series, horizon)
    else:
        selected = "SMA-7"
        final_forecast = _sma_forecast(clean_series, horizon)

    return {
        "selected_model": selected,
        "models_compared": {
            "SMA-7": {"mae": sma_mae, "rmse": sma_rmse},
            "Holt-Linear": {"mae": holt_mae, "rmse": holt_rmse},
            "RidgeRegression": sk_metrics["RidgeRegression"],
            "RandomForestRegressor": sk_metrics["RandomForestRegressor"],
        },
        "forecast": final_forecast,
    }


async def generate_business_ai_forecast(
    db: AsyncSession,
    user_id: Any,
    lookback_days: int = 30,
    horizon_days: int = 7,
) -> dict[str, Any]:
    """
    Generates SKU-level inventory demand forecasts, stockout alerts, and
    daily revenue/cash-flow time-series projections for the authenticated merchant.
    """
    owned_businesses = select(Business.id).where(Business.owner_id == user_id)

    prod_res = await db.execute(select(Product).where(Product.business_id.in_(owned_businesses)))
    products = list(prod_res.scalars().all())

    inv_res = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(
            Invoice.business_id.in_(owned_businesses),
            Invoice.status.in_(["CONFIRMED", "PAID"]),
        )
    )
    invoices = list(inv_res.scalars().all())

    now = datetime.now(UTC)
    start_date = (now - timedelta(days=lookback_days - 1)).date()
    date_grid = [start_date + timedelta(days=i) for i in range(lookback_days)]

    daily_revenue_map: dict[str, float] = {d.isoformat(): 0.0 for d in date_grid}
    daily_outflow_map: dict[str, float] = {d.isoformat(): 0.0 for d in date_grid}
    sku_daily_units: dict[Any, dict[str, float]] = defaultdict(lambda: {d.isoformat(): 0.0 for d in date_grid})

    total_receivables = 0.0
    for inv in invoices:
        inv_date = (inv.created_at.astimezone(UTC) if inv.created_at.tzinfo else inv.created_at.replace(tzinfo=UTC)).date()
        date_key = inv_date.isoformat()

        if inv.type == "SALE":
            outstanding = max(0.0, float(inv.total_amount) - float(inv.paid_amount))
            total_receivables += outstanding
            if date_key in daily_revenue_map:
                daily_revenue_map[date_key] += float(inv.total_amount)
            for item in inv.items:
                if date_key in sku_daily_units[item.product_id]:
                    sku_daily_units[item.product_id][date_key] += float(item.quantity)
        elif inv.type == "PURCHASE" and date_key in daily_outflow_map:
            daily_outflow_map[date_key] += float(inv.total_amount)

    # 1. Revenue & Cash-Flow Time Series Forecasting
    chronological_revenue = [round(daily_revenue_map[d.isoformat()], 2) for d in date_grid]
    rev_eval = evaluate_and_forecast_series(chronological_revenue, horizon=horizon_days)

    forecast_dates = [(now.date() + timedelta(days=i + 1)).isoformat() for i in range(horizon_days)]
    projected_revenue_series = [
        {"date": f_date, "projected_revenue": pred}
        for f_date, pred in zip(forecast_dates, rev_eval["forecast"], strict=False)
    ]

    # 2. SKU-Level Demand Velocity & Stockout Predictions
    sku_forecasts: list[dict[str, Any]] = []
    for prod in products:
        prod_series = [sku_daily_units[prod.id][d.isoformat()] for d in date_grid]
        sku_eval = evaluate_and_forecast_series(prod_series, horizon=horizon_days)
        forecast_7d = round(sum(sku_eval["forecast"]), 2)
        daily_velocity = round(forecast_7d / max(1, horizon_days), 2)
        # Fallback if no sales in window: estimate gentle baseline velocity from stock level
        if daily_velocity == 0.0 and sum(prod_series) > 0:
            daily_velocity = round(sum(prod_series) / lookback_days, 2)

        current_stock = float(prod.stock_qty)
        days_to_stockout = round(current_stock / daily_velocity, 1) if daily_velocity > 0 else 999.0
        forecast_30d = round(daily_velocity * 30.0, 1)
        recommended_reorder = round(max(0.0, forecast_30d - current_stock), 1)

        if current_stock <= 5 or days_to_stockout <= 3.0:
            urgency = "CRITICAL"
        elif days_to_stockout <= 7.0:
            urgency = "WARNING"
        else:
            urgency = "HEALTHY"

        sku_forecasts.append(
            {
                "product_id": str(prod.id),
                "name": prod.name,
                "sku": prod.sku or "—",
                "unit": prod.unit or "units",
                "current_stock": current_stock,
                "daily_velocity": daily_velocity,
                "forecast_7d_units": forecast_7d,
                "forecast_30d_units": forecast_30d,
                "days_to_stockout": days_to_stockout,
                "recommended_reorder_qty": recommended_reorder,
                "urgency": urgency,
                "selected_model": sku_eval["selected_model"],
            }
        )

    urgency_rank = {"CRITICAL": 0, "WARNING": 1, "HEALTHY": 2}
    sku_forecasts.sort(key=lambda x: (urgency_rank.get(x["urgency"], 3), x["days_to_stockout"], -x["forecast_7d_units"]))

    projected_7d_revenue = round(sum(rev_eval["forecast"]), 2)
    critical_count = sum(1 for s in sku_forecasts if s["urgency"] == "CRITICAL")

    insights: list[str] = []
    if critical_count > 0:
        top_crit = [s["name"] for s in sku_forecasts if s["urgency"] == "CRITICAL"][:2]
        insights.append(
            f"Restock Alert: {critical_count} item(s) ({', '.join(top_crit)}) risk stockout within 72 hours based on current sales velocity."
        )
    if total_receivables > 0:
        insights.append(
            f"Working Capital Opportunity: ₹{total_receivables:,.2f} in open customer Udhar can be recovered via UPI payment links."
        )
    insights.append(
        f"Revenue Projection ({rev_eval['selected_model']}): Expected sales of ₹{projected_7d_revenue:,.2f} over the next {horizon_days} days."
    )

    return {
        "generated_at": now.isoformat(),
        "lookback_days": lookback_days,
        "horizon_days": horizon_days,
        "revenue_model": {
            "selected_model": rev_eval["selected_model"],
            "validation_metrics": rev_eval["models_compared"],
            "projected_7d_revenue": projected_7d_revenue,
            "outstanding_receivables": round(total_receivables, 2),
            "historical_daily": [
                {"date": d.isoformat(), "revenue": round(daily_revenue_map[d.isoformat()], 2)}
                for d in date_grid[-14:]
            ],
            "forecast_daily": projected_revenue_series,
        },
        "inventory_forecasts": sku_forecasts[:12],
        "critical_restock_count": critical_count,
        "insights": insights,
    }
