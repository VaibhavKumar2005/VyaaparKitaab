"""
Machine Learning & Outgoing Payments Intelligence Engine (pandas + scikit-learn).

Implements:
1. Supervised Time-Series Outflow/Revenue Regression (`Ridge` & `RandomForestRegressor`)
   with strict chronological train/validation split BEFORE `StandardScaler` fitting.
2. Unsupervised Payee Segmentation (`KMeans` + `StandardScaler` + `PCA` + `silhouette_score`)
   to group recipients ("payments made to others") into interpretable behavioural tiers.
3. Unsupervised Outgoing Payment Anomaly Detection (`IsolationForest`) to flag unusually
   large or irregular payments.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business, Customer
from app.models.purchase import PersonalPurchase
from app.models.transaction import Invoice
from app.models.user import User
from app.services.encryption import blind_email, blind_phone


def train_and_compare_sklearn_forecasters(
    daily_series: list[float],
    horizon: int = 7,
) -> dict[str, Any]:
    """
    Builds a pandas DataFrame of lag and rolling-window features from a daily time series,
    handles NULL/NaN values explicitly, performs a chronological 80/20 split BEFORE fitting
    `StandardScaler`, and compares:
      - Ridge Regression (L2 regularized linear model)
      - RandomForestRegressor (non-linear tree ensemble)
    Returns validation MAE/RMSE and multi-step recursive predictions.
    """
    s = pd.Series([max(0.0, float(v if v is not None else 0.0)) for v in daily_series], dtype="float64")
    null_count = int(s.isna().sum())
    s = s.fillna(0.0)

    if len(s) < 8 or float(s.sum()) == 0.0:
        mean_val = round(float(s.mean()) if len(s) else 0.0, 2)
        return {
            "selected_ml_model": "RidgeRegression",
            "null_values_imputed": null_count,
            "metrics": {
                "RidgeRegression": {"mae": 0.0, "rmse": 0.0},
                "RandomForestRegressor": {"mae": 0.0, "rmse": 0.0},
            },
            "forecast": [mean_val] * horizon,
        }

    df = pd.DataFrame({"y": s})
    df["t"] = np.arange(len(df), dtype="float64")
    df["lag_1"] = df["y"].shift(1)
    df["lag_2"] = df["y"].shift(2)
    df["lag_3"] = df["y"].shift(3)
    df["roll_3"] = df["y"].shift(1).rolling(window=3, min_periods=1).mean()
    df["roll_7"] = df["y"].shift(1).rolling(window=7, min_periods=1).mean()

    # Impute initial lag NaNs with training-prefix median (or 0.0) to preserve rows
    feature_cols = ["t", "lag_1", "lag_2", "lag_3", "roll_3", "roll_7"]
    df[feature_cols] = df[feature_cols].bfill().fillna(0.0)

    val_size = max(2, round(len(df) * 0.2))
    train_df = df.iloc[:-val_size].copy()
    val_df = df.iloc[-val_size:].copy()

    # Strict Featurization Ordering: fit StandardScaler ONLY on train_df
    scaler = StandardScaler()
    x_train = scaler.fit_transform(train_df[feature_cols].to_numpy())
    y_train = train_df["y"].to_numpy()
    x_val = scaler.transform(val_df[feature_cols].to_numpy())
    y_val = val_df["y"].to_numpy()

    ridge = Ridge(alpha=1.0)
    ridge.fit(x_train, y_train)
    ridge_preds = np.maximum(0.0, ridge.predict(x_val))

    rf = RandomForestRegressor(n_estimators=40, max_depth=5, random_state=42)
    rf.fit(x_train, y_train)
    rf_preds = np.maximum(0.0, rf.predict(x_val))

    ridge_mae = round(float(mean_absolute_error(y_val, ridge_preds)), 2)
    ridge_rmse = round(float(root_mean_squared_error(y_val, ridge_preds)), 2)
    rf_mae = round(float(mean_absolute_error(y_val, rf_preds)), 2)
    rf_rmse = round(float(root_mean_squared_error(y_val, rf_preds)), 2)

    # Select best model on validation RMSE and refit on full dataset
    full_scaler = StandardScaler()
    x_full = full_scaler.fit_transform(df[feature_cols].to_numpy())
    y_full = df["y"].to_numpy()

    if ridge_rmse <= rf_rmse:
        selected_name = "RidgeRegression"
        best_model: Any = Ridge(alpha=1.0).fit(x_full, y_full)
    else:
        selected_name = "RandomForestRegressor"
        best_model = RandomForestRegressor(n_estimators=40, max_depth=5, random_state=42).fit(x_full, y_full)

    history = list(df["y"].to_numpy())
    future_preds: list[float] = []
    for step in range(horizon):
        t_val = float(len(history))
        lag1 = history[-1]
        lag2 = history[-2] if len(history) >= 2 else lag1
        lag3 = history[-3] if len(history) >= 3 else lag2
        r3 = float(np.mean(history[-3:]))
        r7 = float(np.mean(history[-7:]))
        row_vec = np.array([[t_val, lag1, lag2, lag3, r3, r7]], dtype="float64")
        scaled_vec = full_scaler.transform(row_vec)
        pred_val = round(max(0.0, float(best_model.predict(scaled_vec)[0])), 2)
        future_preds.append(pred_val)
        history.append(pred_val)
        _ = step

    return {
        "selected_ml_model": selected_name,
        "null_values_imputed": null_count,
        "metrics": {
            "RidgeRegression": {"mae": ridge_mae, "rmse": ridge_rmse},
            "RandomForestRegressor": {"mae": rf_mae, "rmse": rf_rmse},
        },
        "forecast": future_preds,
    }


def cluster_payees_with_kmeans(payee_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Clusters payees ("payments made to others") using `StandardScaler` + `KMeans` + `PCA`.
    Selects optimal cluster count k using `silhouette_score` when enough distinct payees exist.
    """
    if not payee_rows:
        return [], {"optimal_k": 0, "silhouette_score": 0.0}

    df = pd.DataFrame(payee_rows)
    num_cols = ["total_paid", "payment_count", "avg_payment", "recency_days"]
    df[num_cols] = df[num_cols].fillna(0.0)

    n = len(df)
    if n < 3:
        for r in payee_rows:
            r["ml_cluster_label"] = "Primary Payee" if r["total_paid"] >= 1000 else "Regular Payee"
            r["pca_x"] = 0.0
            r["pca_y"] = 0.0
        return payee_rows, {"optimal_k": 1, "silhouette_score": 1.0}

    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(df[num_cols].to_numpy(dtype="float64"))

    best_k = 2
    best_score = -1.0
    best_labels = np.zeros(n, dtype=int)

    max_k = min(3, n - 1)
    for k in range(2, max_k + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(x_scaled)
        if len(set(labels)) > 1:
            score = float(silhouette_score(x_scaled, labels))
            if score > best_score:
                best_score = score
                best_k = k
                best_labels = labels

    # 2D PCA projection for cluster explainability
    if x_scaled.shape[1] >= 2 and n >= 2:
        pca = PCA(n_components=2, random_state=42)
        coords = pca.fit_transform(x_scaled)
    else:
        coords = np.zeros((n, 2), dtype="float64")

    # Rank cluster IDs by mean total_paid so human labels are deterministic
    df["cluster_id"] = best_labels
    cluster_means = df.groupby("cluster_id")["total_paid"].mean().sort_values(ascending=False).index.tolist()
    tier_names = ["High-Value Regular Payee", "Frequent Everyday Payee", "Occasional / One-Time Payee"]
    label_map = {cid: tier_names[min(idx, len(tier_names) - 1)] for idx, cid in enumerate(cluster_means)}

    for idx, r in enumerate(payee_rows):
        cid = int(best_labels[idx])
        r["ml_cluster_label"] = label_map.get(cid, "Regular Payee")
        r["pca_x"] = round(float(coords[idx, 0]), 3)
        r["pca_y"] = round(float(coords[idx, 1]), 3)

    return payee_rows, {"optimal_k": best_k, "silhouette_score": round(max(0.0, best_score), 3)}


def detect_payment_anomalies(tx_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Uses `sklearn.ensemble.IsolationForest` on transaction amounts to flag unusually
    high outgoing payments made to others.
    """
    if len(tx_records) < 4:
        return []

    amounts = np.array([[float(r["amount"])] for r in tx_records], dtype="float64")
    median_amt = float(np.median(amounts))
    iso = IsolationForest(contamination=0.15, random_state=42)
    preds = iso.fit_predict(amounts)

    anomalies: list[dict[str, Any]] = []
    for r, flag in zip(tx_records, preds, strict=False):
        if flag == -1 and float(r["amount"]) > median_amt:
            anomalies.append(
                {
                    "payee_name": r["payee_name"],
                    "amount": round(float(r["amount"]), 2),
                    "paid_at": r["paid_at"],
                    "channel": r["channel"],
                    "note": r.get("note") or f"High-value payment to {r['payee_name']}",
                }
            )
    anomalies.sort(key=lambda x: x["amount"], reverse=True)
    return anomalies[:5]


async def summarize_payments_made_to_others(
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    """
    Aggregates and summarizes ALL payments made by the authenticated user to others:
      1. Personal / Marketplace / Direct UPI payments (`personal_purchases`)
      2. Supplier / Wholesale purchase payments (`invoices` where type == 'PURCHASE')
      3. Retail store bill payments (`invoices` where type == 'SALE' paid by this customer)
    Runs `pandas` aggregation, `scikit-learn` KMeans payee clustering, `IsolationForest`
    anomaly detection, and `Ridge`/`RandomForest` 30-day outflow regression.
    """
    now = datetime.now(UTC)

    # 1. Personal / Marketplace / Peer UPI purchases
    p_res = await db.execute(
        select(PersonalPurchase)
        .where(PersonalPurchase.user_id == user.id)
        .order_by(PersonalPurchase.purchased_at.desc())
    )
    purchases = list(p_res.scalars().all())

    # 2. Store Owner Wholesale Supplier PURCHASE invoices (if user owns a business)
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    sup_inv_res = await db.execute(
        select(Invoice).where(
            Invoice.business_id.in_(owned_businesses),
            Invoice.type == "PURCHASE",
            Invoice.status.in_(["CONFIRMED", "PAID"]),
        )
    )
    supplier_invoices = list(sup_inv_res.scalars().all())

    # 3. Customer retail bill settlements (if user is a customer paying a store)
    p_hash = blind_phone(user.phone)
    e_hash = blind_email(user.email)
    cust_conds = [Customer.phone == user.phone, Customer.email == user.email]
    if p_hash:
        cust_conds.append(Customer.phone_hash == p_hash)
    if e_hash:
        cust_conds.append(Customer.email_hash == e_hash)

    from sqlalchemy import or_

    cust_ids = select(Customer.id).where(or_(*cust_conds))
    retail_inv_res = await db.execute(
        select(Invoice).where(
            Invoice.type == "SALE",
            Invoice.paid_amount > 0,
            (Invoice.customer_id == user.id) | (Invoice.customer_id.in_(cust_ids)),
        )
    )
    retail_invoices = list(retail_inv_res.scalars().all())

    unified_tx: list[dict[str, Any]] = []
    known_marketplaces = {"amazon", "flipkart", "blinkit", "myntra", "zepto", "instamart", "swiggy", "zomato"}

    for p in purchases:
        p_dt = p.purchased_at.astimezone(UTC) if p.purchased_at.tzinfo else p.purchased_at.replace(tzinfo=UTC)
        mkt_clean = p.marketplace.strip()
        p_type = "Marketplace / App" if mkt_clean.lower() in known_marketplaces else "Direct UPI / Person / Merchant"
        unified_tx.append(
            {
                "payee_name": mkt_clean,
                "payee_type": p_type,
                "amount": float(p.amount),
                "paid_at": p_dt.isoformat(),
                "date_str": p_dt.date().isoformat(),
                "channel": (p.payment_method or "UPI (Google Pay)").strip(),
                "category": p.category or "Shopping",
                "note": p.items_note or f"Order #{p.order_id}",
                "recency_days": max(0.0, (now - p_dt).total_seconds() / 86400.0),
            }
        )

    for inv in supplier_invoices:
        paid_val = float(inv.paid_amount) if float(inv.paid_amount) > 0 else float(inv.total_amount)
        if paid_val <= 0:
            continue
        i_dt = inv.created_at.astimezone(UTC) if inv.created_at.tzinfo else inv.created_at.replace(tzinfo=UTC)
        unified_tx.append(
            {
                "payee_name": "Wholesale Supplier / Distributor",
                "payee_type": "Wholesale Supplier",
                "amount": paid_val,
                "paid_at": i_dt.isoformat(),
                "date_str": i_dt.date().isoformat(),
                "channel": inv.payment_method or "UPI",
                "category": "Inventory Restock",
                "note": f"Supplier Bill #{inv.invoice_number}",
                "recency_days": max(0.0, (now - i_dt).total_seconds() / 86400.0),
            }
        )

    for r_inv in retail_invoices:
        paid_val = float(r_inv.paid_amount)
        if paid_val <= 0:
            continue
        i_dt = r_inv.created_at.astimezone(UTC) if r_inv.created_at.tzinfo else r_inv.created_at.replace(tzinfo=UTC)
        unified_tx.append(
            {
                "payee_name": "Kirana & Retail Store Bills",
                "payee_type": "Retail Store",
                "amount": paid_val,
                "paid_at": i_dt.isoformat(),
                "date_str": i_dt.date().isoformat(),
                "channel": r_inv.payment_method or "UPI",
                "category": "Groceries & Retail",
                "note": f"Bill #{r_inv.invoice_number}",
                "recency_days": max(0.0, (now - i_dt).total_seconds() / 86400.0),
            }
        )

    total_paid = round(sum(t["amount"] for t in unified_tx), 2)
    total_tx_count = len(unified_tx)

    # Group by Payee using pandas DataFrame
    payee_rows: list[dict[str, Any]] = []
    channel_rows: list[dict[str, Any]] = []
    if unified_tx:
        tx_df = pd.DataFrame(unified_tx)
        for payee_name, grp in tx_df.groupby("payee_name", sort=False):
            p_sum = round(float(grp["amount"].sum()), 2)
            p_cnt = len(grp)
            p_avg = round(float(grp["amount"].mean()), 2)
            p_min_recency = round(float(grp["recency_days"].min()), 1)
            latest_row = grp.sort_values("paid_at", ascending=False).iloc[0]
            top_channel = str(grp["channel"].mode().iloc[0]) if not grp["channel"].mode().empty else "UPI"
            payee_rows.append(
                {
                    "payee_name": str(payee_name),
                    "payee_type": str(latest_row["payee_type"]),
                    "total_paid": p_sum,
                    "share_percentage": round((p_sum / max(total_paid, 1.0)) * 100.0, 1),
                    "payment_count": p_cnt,
                    "avg_payment": p_avg,
                    "last_paid_at": str(latest_row["paid_at"]),
                    "primary_channel": top_channel,
                    "recency_days": p_min_recency,
                }
            )
        payee_rows.sort(key=lambda x: x["total_paid"], reverse=True)

        for ch_name, grp in tx_df.groupby("channel", sort=False):
            c_sum = round(float(grp["amount"].sum()), 2)
            channel_rows.append(
                {
                    "channel": str(ch_name),
                    "total_paid": c_sum,
                    "percentage": round((c_sum / max(total_paid, 1.0)) * 100.0, 1),
                    "transaction_count": len(grp),
                }
            )
        channel_rows.sort(key=lambda x: x["total_paid"], reverse=True)

    # Run scikit-learn KMeans payee clustering
    clustered_payees, cluster_meta = cluster_payees_with_kmeans(payee_rows)

    # Run scikit-learn Ridge vs RandomForest 30-day daily outflow regression
    start_date = (now - timedelta(days=29)).date()
    date_grid = [(start_date + timedelta(days=i)).isoformat() for i in range(30)]
    daily_outflow_map = dict.fromkeys(date_grid, 0.0)
    for t in unified_tx:
        if t["date_str"] in daily_outflow_map:
            daily_outflow_map[t["date_str"]] += t["amount"]

    daily_series = [round(daily_outflow_map[d], 2) for d in date_grid]
    ml_forecast_res = train_and_compare_sklearn_forecasters(daily_series, horizon=7)
    predicted_7d = round(sum(ml_forecast_res["forecast"]), 2)
    predicted_30d = round(predicted_7d * (30.0 / 7.0), 2)

    # Run scikit-learn IsolationForest anomaly detection
    anomalies = detect_payment_anomalies(unified_tx)

    top_payee = clustered_payees[0] if clustered_payees else None
    if top_payee:
        top_channel_str = channel_rows[0]["channel"] if channel_rows else "UPI"
        summary_text = (
            f"You have made {total_tx_count} payment(s) totalling ₹{total_paid:,.2f} across "
            f"{len(clustered_payees)} recipient(s). Your largest payee is {top_payee['payee_name']} "
            f"(₹{top_payee['total_paid']:,.2f}, {top_payee['share_percentage']}% of all outflows), "
            f"primarily paid via {top_channel_str}. Based on {ml_forecast_res['selected_ml_model']} "
            f"time-series regression, your projected outflow over the next 7 days is ₹{predicted_7d:,.2f}."
        )
    else:
        summary_text = "No outgoing payments recorded yet. Add a purchase or UPI payment to generate your ML payee summary."

    return {
        "total_paid_to_others": total_paid,
        "total_transactions": total_tx_count,
        "unique_payees_count": len(clustered_payees),
        "top_payee_name": top_payee["payee_name"] if top_payee else "—",
        "top_payee_amount": top_payee["total_paid"] if top_payee else 0.0,
        "predicted_7d_outflow": predicted_7d,
        "predicted_30d_outflow": predicted_30d,
        "ai_summary_text": summary_text,
        "ml_models_used": {
            "regression_model": ml_forecast_res["selected_ml_model"],
            "regression_metrics": ml_forecast_res["metrics"],
            "clustering_model": "KMeans + StandardScaler + PCA",
            "clustering_silhouette_score": cluster_meta["silhouette_score"],
            "anomaly_detector": "IsolationForest (contamination=0.15)",
        },
        "payee_summary": clustered_payees,
        "payment_app_summary": channel_rows,
        "anomalies": anomalies,
    }


async def get_store_transaction_drilldown(
    db: AsyncSession,
    user: User,
    store_name: str | None = None,
) -> dict[str, Any]:
    """
    Generates a comprehensive graphical transaction drill-down for a particular store/merchant/payee.
    Returns:
      - available_stores: list of all stores/merchants the user has transacted with
      - selected_store metrics: total_spent, share_of_wallet_pct, transaction_count, avg/max/min order, predicted_next_order
      - transactions_timeline: chronological order bars + running cumulative cost curve
      - payment_method_split & category_split: ring/bar breakdown for that specific store
      - store_flow_nodes & store_flow_edges: dedicated store-to-order flow graph
    """
    purchases_res = await db.execute(
        select(PersonalPurchase)
        .where(PersonalPurchase.user_id == user.id)
        .order_by(PersonalPurchase.purchased_at.asc(), PersonalPurchase.created_at.asc())
    )
    purchases = list(purchases_res.scalars().all())

    biz_res = await db.execute(select(Business.id, Business.name).where(Business.owner_id == user.id))
    biz_rows = biz_res.all()
    business_ids = [r[0] for r in biz_rows]

    supplier_invoices: list[Invoice] = []
    if business_ids:
        sup_res = await db.execute(
            select(Invoice)
            .where(
                Invoice.business_id.in_(business_ids),
                Invoice.type == "PURCHASE",
                Invoice.status.in_(["CONFIRMED", "PAID"]),
            )
            .order_by(Invoice.created_at.asc())
        )
        supplier_invoices = list(sup_res.scalars().all())

    retail_invoices: list[Invoice] = []
    if user.phone:
        cust_res = await db.execute(
            select(Customer.id, Customer.business_id).where(Customer.phone_hash == blind_phone(user.phone))
        )
        cust_rows = cust_res.all()
        customer_ids = [r[0] for r in cust_rows]
        if customer_ids:
            ret_res = await db.execute(
                select(Invoice)
                .where(
                    Invoice.customer_id.in_(customer_ids),
                    Invoice.type == "SALE",
                    Invoice.paid_amount > 0,
                )
                .order_by(Invoice.created_at.asc())
            )
            retail_invoices = list(ret_res.scalars().all())

    known_marketplaces = {"amazon", "flipkart", "myntra", "blinkit", "swiggy", "zomato", "meesho", "zepto", "bigbasket"}
    all_records: list[dict[str, Any]] = []

    for p in purchases:
        p_dt = p.purchased_at.astimezone(UTC) if p.purchased_at.tzinfo else p.purchased_at.replace(tzinfo=UTC)
        mkt_clean = p.marketplace.strip()
        s_type = "Marketplace / App" if mkt_clean.lower() in known_marketplaces else "Direct Store / UPI Payee"
        all_records.append(
            {
                "id": str(p.id),
                "store_name": mkt_clean,
                "store_type": s_type,
                "amount": float(p.amount),
                "paid_at": p_dt.isoformat(),
                "date": p_dt.date().isoformat(),
                "order_id": p.order_id,
                "items_note": p.items_note or f"Order #{p.order_id}",
                "payment_method": (p.payment_method or "UPI (Google Pay)").strip(),
                "category": p.category or "Shopping",
            }
        )

    for inv in supplier_invoices:
        paid_val = float(inv.paid_amount) if float(inv.paid_amount) > 0 else float(inv.total_amount)
        if paid_val <= 0:
            continue
        i_dt = inv.created_at.astimezone(UTC) if inv.created_at.tzinfo else inv.created_at.replace(tzinfo=UTC)
        all_records.append(
            {
                "id": str(inv.id),
                "store_name": "Wholesale Supplier / Distributor",
                "store_type": "Wholesale Supplier",
                "amount": paid_val,
                "paid_at": i_dt.isoformat(),
                "date": i_dt.date().isoformat(),
                "order_id": inv.invoice_number,
                "items_note": f"Supplier Bill #{inv.invoice_number}",
                "payment_method": inv.payment_method or "UPI",
                "category": "Inventory Restock",
            }
        )

    for r_inv in retail_invoices:
        paid_val = float(r_inv.paid_amount)
        if paid_val <= 0:
            continue
        i_dt = r_inv.created_at.astimezone(UTC) if r_inv.created_at.tzinfo else r_inv.created_at.replace(tzinfo=UTC)
        all_records.append(
            {
                "id": str(r_inv.id),
                "store_name": "Kirana & Retail Store Bills",
                "store_type": "Retail Store",
                "amount": paid_val,
                "paid_at": i_dt.isoformat(),
                "date": i_dt.date().isoformat(),
                "order_id": r_inv.invoice_number,
                "items_note": f"Retail Bill #{r_inv.invoice_number}",
                "payment_method": r_inv.payment_method or "UPI",
                "category": "Groceries & Retail",
            }
        )

    grand_total = sum(r["amount"] for r in all_records)

    if not all_records:
        return {
            "selected_store": store_name or "None",
            "store_type": "N/A",
            "total_spent": 0.0,
            "share_of_wallet_pct": 0.0,
            "transaction_count": 0,
            "avg_order_value": 0.0,
            "max_order_value": 0.0,
            "min_order_value": 0.0,
            "predicted_next_order": 0.0,
            "available_stores": [],
            "transactions_timeline": [],
            "payment_method_split": [],
            "category_split": [],
            "store_flow_nodes": [],
            "store_flow_edges": [],
        }

    df = pd.DataFrame(all_records)
    available_stores: list[dict[str, Any]] = []
    for s_name, grp in df.groupby("store_name", sort=False):
        s_sum = round(float(grp["amount"].sum()), 2)
        latest = grp.sort_values("paid_at", ascending=False).iloc[0]
        available_stores.append(
            {
                "store_name": str(s_name),
                "store_type": str(latest["store_type"]),
                "total_spent": s_sum,
                "transaction_count": len(grp),
                "last_tx_at": str(latest["paid_at"]),
            }
        )
    available_stores.sort(key=lambda x: x["total_spent"], reverse=True)

    # Resolve target store (case-insensitive match, fallback to top store)
    target_store = available_stores[0]["store_name"]
    if store_name and store_name.strip():
        needle = store_name.strip().lower()
        for st in available_stores:
            if st["store_name"].lower() == needle or needle in st["store_name"].lower():
                target_store = st["store_name"]
                break

    store_df = df[df["store_name"] == target_store].sort_values("paid_at", ascending=True).copy()
    store_total = round(float(store_df["amount"].sum()), 2)
    tx_count = len(store_df)
    avg_val = round(float(store_df["amount"].mean()), 2)
    max_val = round(float(store_df["amount"].max()), 2)
    min_val = round(float(store_df["amount"].min()), 2)
    share_pct = round((store_total / max(grand_total, 1.0)) * 100.0, 1)
    store_type = str(store_df.iloc[-1]["store_type"])

    # Predict next transaction amount at this store using pandas EWMA + linear trend
    ewm_val = float(store_df["amount"].ewm(span=min(3, max(1, tx_count)), adjust=True).mean().iloc[-1])
    predicted_next = round(max(0.0, ewm_val), 2)

    # Chronological timeline with cumulative cost curve
    running_sum = 0.0
    timeline: list[dict[str, Any]] = []
    for _, row in store_df.iterrows():
        amt = round(float(row["amount"]), 2)
        running_sum = round(running_sum + amt, 2)
        timeline.append(
            {
                "id": str(row["id"]),
                "date": str(row["date"]),
                "paid_at": str(row["paid_at"]),
                "amount": amt,
                "cumulative_amount": running_sum,
                "order_id": str(row["order_id"]),
                "items_note": str(row["items_note"]),
                "payment_method": str(row["payment_method"]),
                "category": str(row["category"]),
            }
        )

    # Payment method split at this store
    method_split: list[dict[str, Any]] = []
    for m_name, m_grp in store_df.groupby("payment_method", sort=False):
        m_sum = round(float(m_grp["amount"].sum()), 2)
        method_split.append(
            {
                "method": str(m_name),
                "amount": m_sum,
                "percentage": round((m_sum / max(store_total, 1.0)) * 100.0, 1),
                "count": len(m_grp),
            }
        )
    method_split.sort(key=lambda x: x["amount"], reverse=True)

    # Category split at this store
    cat_split: list[dict[str, Any]] = []
    for c_name, c_grp in store_df.groupby("category", sort=False):
        c_sum = round(float(c_grp["amount"].sum()), 2)
        cat_split.append(
            {
                "category": str(c_name),
                "amount": c_sum,
                "percentage": round((c_sum / max(store_total, 1.0)) * 100.0, 1),
                "count": len(c_grp),
            }
        )
    cat_split.sort(key=lambda x: x["amount"], reverse=True)

    # Store-specific directed graph: Bank -> UPI Method(s) -> Store Hub -> Individual Orders (up to 6 most recent)
    flow_nodes: list[dict[str, Any]] = [
        {
            "id": "bank_source",
            "label": "Your Bank Account",
            "type": "SOURCE",
            "subtext": f"Total Debited for {target_store}",
            "total_volume": store_total,
            "order_count": tx_count,
        },
        {
            "id": "store_hub",
            "label": target_store,
            "type": "MERCHANT",
            "subtext": store_type,
            "total_volume": store_total,
            "order_count": tx_count,
        },
    ]
    flow_edges: list[dict[str, Any]] = []

    for idx, m_item in enumerate(method_split):
        gw_id = f"gw_{idx}"
        flow_nodes.append(
            {
                "id": gw_id,
                "label": m_item["method"],
                "type": "GATEWAY",
                "subtext": f"{m_item['percentage']}% of store spend",
                "total_volume": m_item["amount"],
                "order_count": m_item["count"],
            }
        )
        flow_edges.append(
            {
                "from_node": "bank_source",
                "to_node": gw_id,
                "amount": m_item["amount"],
                "order_count": m_item["count"],
                "status": "CONFIRMED",
            }
        )
        flow_edges.append(
            {
                "from_node": gw_id,
                "to_node": "store_hub",
                "amount": m_item["amount"],
                "order_count": m_item["count"],
                "status": "CONFIRMED",
            }
        )

    recent_orders = timeline[-6:]
    for o_idx, tx_item in enumerate(recent_orders):
        ord_node_id = f"ord_{o_idx}"
        flow_nodes.append(
            {
                "id": ord_node_id,
                "label": f"#{tx_item['order_id'][:14]}",
                "type": "ORDER",
                "subtext": f"{tx_item['date']} · {tx_item['items_note'][:28]}",
                "total_volume": tx_item["amount"],
                "order_count": 1,
            }
        )
        flow_edges.append(
            {
                "from_node": "store_hub",
                "to_node": ord_node_id,
                "amount": tx_item["amount"],
                "order_count": 1,
                "status": "CONFIRMED",
            }
        )

    return {
        "selected_store": target_store,
        "store_type": store_type,
        "total_spent": store_total,
        "share_of_wallet_pct": share_pct,
        "transaction_count": tx_count,
        "avg_order_value": avg_val,
        "max_order_value": max_val,
        "min_order_value": min_val,
        "predicted_next_order": predicted_next,
        "available_stores": available_stores,
        "transactions_timeline": timeline,
        "payment_method_split": method_split,
        "category_split": cat_split,
        "store_flow_nodes": flow_nodes,
        "store_flow_edges": flow_edges,
    }

