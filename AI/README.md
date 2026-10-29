# VyaparKitaab AI/ML Demand & Cash-Flow Forecasting Module

This module implements the **AI/ML Demand Forecasting & Cash-Flow Analytics Engine** for VyaparKitaab:

- **Chronological Train / Validation Split (80% / 20%)**: Prevents temporal data leakage when evaluating time-series models.
- **Model Comparison & Selection**:
  - **Baseline**: 7-Day Simple Moving Average (`SMA-7`)
  - **Primary**: Holt's Two-Parameter Double Exponential Smoothing (`Holt-Linear`, $\alpha=0.35, \beta=0.15$ with damped trend clamping)
  - Evaluated via **MAE** (Mean Absolute Error) and **RMSE** (Root Mean Squared Error) on the chronological validation split; the winning model is retrained on 100% of the series to generate 7-day and 30-day projections.
- **SKU-Level Stockout & Reorder Recommendations**: Computes daily unit velocity, days-to-stockout, recommended reorder quantity, and urgency tier (`CRITICAL`, `WARNING`, `HEALTHY`).
- **Live API Endpoint**: Exposed at `GET /api/v1/ai/forecast` and rendered in the Merchant Store Dashboard (`StoreDashboard.tsx`).

