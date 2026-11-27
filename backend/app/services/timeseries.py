"""
Unified Cashflow Time-Series & Multi-Model Forecasting Engine.

Aggregates ALL streamlined financial sources from `unified_transactions` (bank/UPI SMS
messages, Razorpay synced payments, uploaded statements, OCR receipts, and store invoices)
into continuous chronological daily or weekly time series with:
  - Exact Decimal summation per bucket (inflow, outflow, net cashflow, cumulative balance)
  - 7-day rolling moving averages & day-of-week seasonality profiles
  - Robust statistical daily anomaly detection
  - Chronological 80/20 walk-forward comparison across 4 models:
      SMA-7, Holt-Linear Exponential Smoothing, RidgeRegression, and RandomForestRegressor
  - Empirical 80% prediction intervals (`lower` / `upper`) for both inflow and outflow forecasts
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.money import ZERO, money_to_float, to_money
from app.models.unified_transaction import UnifiedTransaction
from app.models.user import User
from app.services.forecasting import _compute_mae_rmse, _holt_linear_forecast, _sma_forecast
from app.services.ml_models import train_and_compare_sklearn_forecasters
from app.services.unified_ledger import _unified_access_clause, backfill_user_unified_ledger

_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _source_bucket(source_type: str) -> str:
    low = (source_type or "").lower()
    if low.startswith("upi_bridge"):
        return "sms_upi"
    if low.startswith("razorpay"):
        return "razorpay"
    if low.startswith("store_"):
        return "store_invoice"
    if low.startswith("personal_purchase"):
        return "ocr_purchase"
    return "statement"


def _evaluate_four_models(series: list[float], horizon: int) -> dict[str, Any]:
    """
    Evaluates SMA-7, Holt-Linear, RidgeRegression, and RandomForestRegressor on an 80/20
    chronological split, selects the lowest-RMSE winner, and returns forecast + 80% bands.
    """
    clean = [max(0.0, float(v or 0.0)) for v in series]
    n = len(clean)
    if n < 5 or sum(clean) == 0.0:
        preds = _sma_forecast(clean, horizon)
        return {
            "selected_model": "SMA-7",
            "metrics": {
                "SMA-7": {"mae": 0.0, "rmse": 0.0},
                "Holt-Linear": {"mae": 0.0, "rmse": 0.0},
                "RidgeRegression": {"mae": 0.0, "rmse": 0.0},
                "RandomForestRegressor": {"mae": 0.0, "rmse": 0.0},
            },
            "forecast": preds,
            "lower": [round(max(0.0, p * 0.85), 2) for p in preds],
            "upper": [round(p * 1.15, 2) for p in preds],
        }

    val_size = max(2, round(n * 0.2))
    train = clean[:-val_size]
    val = clean[-val_size:]

    sma_val = _sma_forecast(train, val_size)
    holt_val = _holt_linear_forecast(train, val_size)
    sma_mae, sma_rmse = _compute_mae_rmse(val, sma_val)
    holt_mae, holt_rmse = _compute_mae_rmse(val, holt_val)

    sk_res = train_and_compare_sklearn_forecasters(clean, horizon=horizon)
    sk_metrics = sk_res["metrics"]

    candidates: dict[str, tuple[float, list[float]]] = {
        "SMA-7": (sma_rmse, _sma_forecast(clean, horizon)),
        "Holt-Linear": (holt_rmse, _holt_linear_forecast(clean, horizon)),
    }
    if n >= 8:
        ridge_rmse = float(sk_metrics["RidgeRegression"]["rmse"])
        rf_rmse = float(sk_metrics["RandomForestRegressor"]["rmse"])
        best_sk_name = str(sk_res["selected_ml_model"])
        best_sk_rmse = ridge_rmse if best_sk_name == "RidgeRegression" else rf_rmse
        candidates[best_sk_name] = (best_sk_rmse, [round(max(0.0, float(v)), 2) for v in sk_res["forecast"]])

    selected_name, (winner_rmse, winner_preds) = min(candidates.items(), key=lambda kv: kv[1][0])

    # Empirical 80% interval (~1.28 * RMSE scaled gently with forecast step sqrt(h))
    band_base = winner_rmse if winner_rmse > 0 else (sum(clean) / max(n, 1)) * 0.2
    lower = [round(max(0.0, p - 1.28 * band_base * math.sqrt((idx + 1) / 3.0)), 2) for idx, p in enumerate(winner_preds)]
    upper = [round(p + 1.28 * band_base * math.sqrt((idx + 1) / 3.0), 2) for idx, p in enumerate(winner_preds)]

    return {
        "selected_model": selected_name,
        "metrics": {
            "SMA-7": {"mae": sma_mae, "rmse": sma_rmse},
            "Holt-Linear": {"mae": holt_mae, "rmse": holt_rmse},
            "RidgeRegression": sk_metrics["RidgeRegression"],
            "RandomForestRegressor": sk_metrics["RandomForestRegressor"],
        },
        "forecast": winner_preds,
        "lower": lower,
        "upper": upper,
    }


def _detect_daily_anomalies(
    dates: list[str],
    values: list[float],
    kind: str,
) -> dict[str, str]:
    non_zero = [v for v in values if v > 0]
    if len(non_zero) < 4:
        return {}
    mean_v = sum(non_zero) / len(non_zero)
    variance = sum((v - mean_v) ** 2 for v in non_zero) / len(non_zero)
    std_v = math.sqrt(variance)
    if std_v <= 1e-6:
        return {}

    flagged: dict[str, str] = {}
    threshold = mean_v + 2.0 * std_v
    for d, v in zip(dates, values, strict=False):
        if v > threshold and v >= mean_v * 1.6:
            ratio = round(v / max(mean_v, 1.0), 1)
            flagged[d] = f"Unusual {kind} spike ({ratio}x normal daily average)"
    return flagged


async def build_cashflow_timeseries(
    db: AsyncSession,
    user: User,
    *,
    lookback_days: int = 30,
    horizon_days: int = 14,
    granularity: str = "daily",
    view: str = "all",
) -> dict[str, Any]:
    """
    Constructs a chronological time series over all user-scoped streamlined transactions
    (SMS/UPI bridge, Razorpay, statements, OCR bills, and store invoices) with 4-model
    forecasting, confidence intervals, seasonality, and anomaly flags.
    """
    await backfill_user_unified_ledger(db, user)

    now = datetime.now(UTC)
    end_date = now.date()
    start_date = end_date - timedelta(days=lookback_days - 1)
    start_dt = datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC)

    stmt = select(UnifiedTransaction).where(
        _unified_access_clause(user, view=view),
        UnifiedTransaction.status != "CANCELLED",
        UnifiedTransaction.occurred_at >= start_dt,
    )
    if (view or "all").lower() == "customer":
        stmt = stmt.where(UnifiedTransaction.status != "DRAFT")

    rows = list((await db.execute(stmt)).scalars().all())

    date_grid: list[date] = [start_date + timedelta(days=i) for i in range(lookback_days)]
    inflow_dec: dict[str, Decimal] = {d.isoformat(): ZERO for d in date_grid}
    outflow_dec: dict[str, Decimal] = {d.isoformat(): ZERO for d in date_grid}
    counts: dict[str, int] = {d.isoformat(): 0 for d in date_grid}
    source_totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
    source_counts: dict[str, int] = defaultdict(int)

    for r in rows:
        dt = r.occurred_at.astimezone(UTC) if r.occurred_at.tzinfo else r.occurred_at.replace(tzinfo=UTC)
        key = dt.date().isoformat()
        if key not in inflow_dec:
            continue
        amt = to_money(r.amount)
        counts[key] += 1
        bucket = _source_bucket(r.source_type)
        source_totals[bucket] += amt
        source_counts[bucket] += 1

        # Store sales linked to a customer have direction=DEBIT (from consumer view) & side=BOTH
        is_store_view = (view or "all").lower() == "store"
        if r.direction == "CREDIT" or (is_store_view and r.source_type == "store_sale"):
            inflow_dec[key] += amt
        else:
            outflow_dec[key] += amt

    date_keys = [d.isoformat() for d in date_grid]
    daily_in = [money_to_float(inflow_dec[k]) for k in date_keys]
    daily_out = [money_to_float(outflow_dec[k]) for k in date_keys]

    inflow_anomalies = _detect_daily_anomalies(date_keys, daily_in, "inflow")
    outflow_anomalies = _detect_daily_anomalies(date_keys, daily_out, "outflow")

    historical_daily: list[dict[str, Any]] = []
    anomalies_list: list[dict[str, Any]] = []
    running_cum = ZERO
    for idx, k in enumerate(date_keys):
        in_d = inflow_dec[k]
        out_d = outflow_dec[k]
        net_d = in_d - out_d
        running_cum += net_d

        win_start = max(0, idx - 6)
        win_len = Decimal(idx - win_start + 1)
        r7_in = sum((inflow_dec[date_keys[j]] for j in range(win_start, idx + 1)), ZERO) / win_len
        r7_out = sum((outflow_dec[date_keys[j]] for j in range(win_start, idx + 1)), ZERO) / win_len

        reason = outflow_anomalies.get(k) or inflow_anomalies.get(k)
        if reason:
            anomalies_list.append(
                {
                    "date": k,
                    "inflow": money_to_float(in_d),
                    "outflow": money_to_float(out_d),
                    "reason": reason,
                }
            )
        historical_daily.append(
            {
                "date": k,
                "inflow": money_to_float(in_d),
                "outflow": money_to_float(out_d),
                "net_cashflow": money_to_float(net_d),
                "cumulative_net": money_to_float(running_cum),
                "rolling_7d_inflow": money_to_float(r7_in),
                "rolling_7d_outflow": money_to_float(r7_out),
                "txn_count": counts[k],
                "is_anomaly": bool(reason),
                "anomaly_reason": reason,
            }
        )

    # Optional weekly rollup for the chart while still forecasting on daily series
    if granularity.strip().lower() == "weekly":
        historical_points: list[dict[str, Any]] = []
        for i in range(0, len(historical_daily), 7):
            chunk = historical_daily[i : i + 7]
            c_in = sum((to_money(p["inflow"]) for p in chunk), ZERO)
            c_out = sum((to_money(p["outflow"]) for p in chunk), ZERO)
            historical_points.append(
                {
                    "date": chunk[0]["date"],
                    "inflow": money_to_float(c_in),
                    "outflow": money_to_float(c_out),
                    "net_cashflow": money_to_float(c_in - c_out),
                    "cumulative_net": chunk[-1]["cumulative_net"],
                    "rolling_7d_inflow": chunk[-1]["rolling_7d_inflow"],
                    "rolling_7d_outflow": chunk[-1]["rolling_7d_outflow"],
                    "txn_count": sum(p["txn_count"] for p in chunk),
                    "is_anomaly": any(p["is_anomaly"] for p in chunk),
                    "anomaly_reason": next((p["anomaly_reason"] for p in chunk if p["anomaly_reason"]), None),
                }
            )
    else:
        historical_points = historical_daily

    # Multi-model chronological forecast for both Inflow and Outflow
    inflow_fc = _evaluate_four_models(daily_in, horizon=horizon_days)
    outflow_fc = _evaluate_four_models(daily_out, horizon=horizon_days)

    forecast_points: list[dict[str, Any]] = []
    proj_in_total = ZERO
    proj_out_total = ZERO
    for i in range(horizon_days):
        f_date = (end_date + timedelta(days=i + 1)).isoformat()
        p_in = to_money(inflow_fc["forecast"][i])
        p_out = to_money(outflow_fc["forecast"][i])
        proj_in_total += p_in
        proj_out_total += p_out
        forecast_points.append(
            {
                "date": f_date,
                "projected_inflow": money_to_float(p_in),
                "inflow_lower": inflow_fc["lower"][i],
                "inflow_upper": inflow_fc["upper"][i],
                "projected_outflow": money_to_float(p_out),
                "outflow_lower": outflow_fc["lower"][i],
                "outflow_upper": outflow_fc["upper"][i],
                "projected_net": money_to_float(p_in - p_out),
            }
        )

    # Day-of-week seasonality profile
    dow_in: dict[int, list[Decimal]] = defaultdict(list)
    dow_out: dict[int, list[Decimal]] = defaultdict(list)
    for d in date_grid:
        k = d.isoformat()
        dow_in[d.weekday()].append(inflow_dec[k])
        dow_out[d.weekday()].append(outflow_dec[k])

    seasonality = []
    for wd in range(7):
        ins = dow_in[wd]
        outs = dow_out[wd]
        avg_i = sum(ins, ZERO) / Decimal(max(len(ins), 1))
        avg_o = sum(outs, ZERO) / Decimal(max(len(outs), 1))
        seasonality.append(
            {
                "day": _WEEKDAY_NAMES[wd],
                "avg_inflow": money_to_float(avg_i),
                "avg_outflow": money_to_float(avg_o),
                "avg_net": money_to_float(avg_i - avg_o),
            }
        )

    # Period growth (second half vs first half of lookback window)
    mid = max(1, lookback_days // 2)
    first_in = sum((inflow_dec[k] for k in date_keys[:mid]), ZERO)
    second_in = sum((inflow_dec[k] for k in date_keys[mid:]), ZERO)
    first_out = sum((outflow_dec[k] for k in date_keys[:mid]), ZERO)
    second_out = sum((outflow_dec[k] for k in date_keys[mid:]), ZERO)

    def _growth_pct(prev: Decimal, curr: Decimal) -> float:
        if prev <= ZERO:
            return 100.0 if curr > ZERO else 0.0
        return round(float(((curr - prev) / prev) * Decimal(100)), 1)

    in_growth = _growth_pct(first_in, second_in)
    out_growth = _growth_pct(first_out, second_out)
    total_in = sum(inflow_dec.values(), ZERO)
    total_out = sum(outflow_dec.values(), ZERO)
    net_total = total_in - total_out

    return {
        "generated_at": now.isoformat(),
        "lookback_days": lookback_days,
        "horizon_days": horizon_days,
        "granularity": granularity.strip().lower(),
        "view": view,
        "summary": {
            "total_inflow": money_to_float(total_in),
            "total_outflow": money_to_float(total_out),
            "net_cashflow": money_to_float(net_total),
            "avg_daily_inflow": money_to_float(total_in / Decimal(max(lookback_days, 1))),
            "avg_daily_outflow": money_to_float(total_out / Decimal(max(lookback_days, 1))),
            "projected_inflow_total": money_to_float(proj_in_total),
            "projected_outflow_total": money_to_float(proj_out_total),
            "projected_net_total": money_to_float(proj_in_total - proj_out_total),
            "inflow_growth_pct": in_growth,
            "outflow_growth_pct": out_growth,
            "total_transactions": sum(counts.values()),
            "anomaly_count": len(anomalies_list),
        },
        "models": {
            "inflow_selected": inflow_fc["selected_model"],
            "outflow_selected": outflow_fc["selected_model"],
            "inflow_metrics": inflow_fc["metrics"],
            "outflow_metrics": outflow_fc["metrics"],
        },
        "sources": [
            {
                "source": src,
                "volume": money_to_float(vol),
                "count": source_counts[src],
            }
            for src, vol in sorted(source_totals.items(), key=lambda x: x[1], reverse=True)
        ],
        "historical": historical_points,
        "forecast": forecast_points,
        "seasonality": seasonality,
        "anomalies": anomalies_list,
    }
