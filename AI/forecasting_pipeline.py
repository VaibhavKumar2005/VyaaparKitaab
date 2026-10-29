"""
VyaparKitaab AI/ML Demand Forecasting & Outgoing Payments Intelligence Pipeline.
Uses pandas + scikit-learn (Ridge, RandomForestRegressor, KMeans, IsolationForest,
StandardScaler, PCA, silhouette_score) alongside Holt-Linear Exponential Smoothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.forecasting import (
    _compute_mae_rmse,
    _holt_linear_forecast,
    _sma_forecast,
    evaluate_and_forecast_series,
    generate_business_ai_forecast,
)
from app.services.ml_models import (
    cluster_payees_with_kmeans,
    detect_payment_anomalies,
    summarize_payments_made_to_others,
    train_and_compare_sklearn_forecasters,
)

__all__ = [
    "_compute_mae_rmse",
    "_holt_linear_forecast",
    "_sma_forecast",
    "cluster_payees_with_kmeans",
    "detect_payment_anomalies",
    "evaluate_and_forecast_series",
    "generate_business_ai_forecast",
    "summarize_payments_made_to_others",
    "train_and_compare_sklearn_forecasters",
]


if __name__ == "__main__":
    sample_daily_sales = [
        4200.0, 4550.0, 4100.0, 4800.0, 5100.0, 5400.0, 5250.0,
        5600.0, 5900.0, 6100.0, 5850.0, 6300.0, 6700.0, 6950.0,
    ]
    result = evaluate_and_forecast_series(sample_daily_sales, horizon=7)
    print(f"Selected Model: {result['selected_model']}")
    print(f"Validation Metrics (SMA-7 / Holt-Linear / Ridge / RandomForest): {result['models_compared']}")
    print(f"7-Day Revenue Forecast (INR): {result['forecast']}")
