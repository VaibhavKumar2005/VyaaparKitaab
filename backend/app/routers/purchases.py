from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.database import get_db
from app.models.purchase import PersonalPurchase
from app.models.user import User
from app.schemas.purchase import (
    CategoryBreakdownItem,
    DailySpendingItem,
    MarketplaceBreakdownItem,
    OutgoingPaymentsSummaryResponse,
    ParsedInvoiceResponse,
    ParseInvoiceTextRequest,
    PersonalSpendingAnalytics,
    PurchaseCreate,
    PurchaseRead,
    StoreDrilldownResponse,
    TransactionGraphEdge,
    TransactionGraphNode,
    TransactionGraphResponse,
)
from app.services.auth import get_current_user
from app.services.encryption import blind_index
from app.services.invoice_parser import parse_marketplace_receipt_text
from app.services.ml_models import (
    get_store_transaction_drilldown,
    summarize_payments_made_to_others,
)

router = APIRouter(prefix="/purchases", tags=["purchases"])


@router.post("", response_model=PurchaseRead, status_code=status.HTTP_201_CREATED)
async def create_purchase(
    payload: PurchaseCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Records a personal marketplace purchase (Amazon, Flipkart, etc.).
    Fields like order_id and items_note are encrypted at rest with AES-128 Fernet.
    Enforces strict user isolation and duplicate check via HMAC blind index.
    """
    bidx = blind_index(payload.order_id)
    dup_check = await db.execute(
        select(PersonalPurchase).where(
            PersonalPurchase.user_id == user.id,
            PersonalPurchase.marketplace == payload.marketplace.strip(),
            PersonalPurchase.order_id_bidx == bidx,
        )
    )
    if dup_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order '{payload.order_id}' on {payload.marketplace} is already recorded.",
        )

    purchase = PersonalPurchase(
        user_id=user.id,
        marketplace=payload.marketplace.strip(),
        category=payload.category.strip() or "Shopping",
        amount=payload.amount,
        currency=payload.currency,
        purchased_at=payload.purchased_at,
        order_id=payload.order_id,
        order_id_bidx=bidx,
        items_note=payload.items_note,
        payment_method=payload.payment_method,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)
    return purchase


@router.get("", response_model=list[PurchaseRead])
async def list_purchases(
    marketplace: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns user-scoped personal purchases with decrypted fields.
    Strictly isolated: users cannot retrieve or leak other tenants' data.
    """
    stmt = select(PersonalPurchase).where(PersonalPurchase.user_id == user.id)
    if marketplace:
        stmt = stmt.where(PersonalPurchase.marketplace.ilike(f"%{marketplace.strip()}%"))
    stmt = stmt.order_by(PersonalPurchase.purchased_at.desc(), PersonalPurchase.created_at.desc())
    stmt = stmt.limit(limit).offset(offset)
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.get("/analytics", response_model=PersonalSpendingAnalytics)
async def get_spending_analytics(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Calculates real-time personal spending metrics:
    - Today's cost incurred
    - 7-day and 30-day costs
    - Daily spending trend
    - Marketplace breakdown (Amazon vs others)
    - Category distribution
    """
    now = datetime.now(UTC)
    today_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=UTC)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)
    past_14_days = now - timedelta(days=14)

    # 1. Period totals
    today_res = await db.execute(
        select(func.coalesce(func.sum(PersonalPurchase.amount), 0.0)).where(
            PersonalPurchase.user_id == user.id,
            PersonalPurchase.purchased_at >= today_start,
        )
    )
    today_cost = float(today_res.scalar_one())

    week_res = await db.execute(
        select(func.coalesce(func.sum(PersonalPurchase.amount), 0.0)).where(
            PersonalPurchase.user_id == user.id,
            PersonalPurchase.purchased_at >= week_start,
        )
    )
    week_cost = float(week_res.scalar_one())

    month_res = await db.execute(
        select(func.coalesce(func.sum(PersonalPurchase.amount), 0.0)).where(
            PersonalPurchase.user_id == user.id,
            PersonalPurchase.purchased_at >= month_start,
        )
    )
    month_cost = float(month_res.scalar_one())

    orders_res = await db.execute(
        select(func.count(PersonalPurchase.id)).where(PersonalPurchase.user_id == user.id)
    )
    total_orders = int(orders_res.scalar_one())

    # 2. Marketplace Breakdown
    mkt_res = await db.execute(
        select(
            PersonalPurchase.marketplace,
            func.sum(PersonalPurchase.amount).label("total"),
            func.count(PersonalPurchase.id).label("cnt"),
        )
        .where(PersonalPurchase.user_id == user.id)
        .group_by(PersonalPurchase.marketplace)
        .order_by(func.sum(PersonalPurchase.amount).desc())
    )
    mkt_rows = mkt_res.all()
    all_spending = sum(float(r[1]) for r in mkt_rows) or 1.0
    marketplace_breakdown = [
        MarketplaceBreakdownItem(
            marketplace=r[0],
            total_cost=round(float(r[1]), 2),
            order_count=int(r[2]),
            percentage=round((float(r[1]) / all_spending) * 100, 1),
        )
        for r in mkt_rows
    ]

    # 3. Category Breakdown
    cat_res = await db.execute(
        select(
            PersonalPurchase.category,
            func.sum(PersonalPurchase.amount).label("total"),
        )
        .where(PersonalPurchase.user_id == user.id)
        .group_by(PersonalPurchase.category)
        .order_by(func.sum(PersonalPurchase.amount).desc())
    )
    cat_rows = cat_res.all()
    category_breakdown = [
        CategoryBreakdownItem(
            category=r[0],
            total_cost=round(float(r[1]), 2),
            percentage=round((float(r[1]) / all_spending) * 100, 1),
        )
        for r in cat_rows
    ]

    # 4. Daily Trend (past 14 days)
    daily_res = await db.execute(
        select(
            cast(PersonalPurchase.purchased_at, Date).label("d"),
            PersonalPurchase.marketplace,
            PersonalPurchase.amount,
        )
        .where(
            PersonalPurchase.user_id == user.id,
            PersonalPurchase.purchased_at >= past_14_days,
        )
        .order_by(cast(PersonalPurchase.purchased_at, Date).asc())
    )
    daily_map: dict[str, dict] = {}
    for row in daily_res.all():
        d_val = row[0]
        day_str = d_val.strftime("%Y-%m-%d") if hasattr(d_val, "strftime") else str(d_val)
        if day_str not in daily_map:
            daily_map[day_str] = {"total_cost": 0.0, "order_count": 0, "marketplaces": set()}
        daily_map[day_str]["total_cost"] += float(row[2])
        daily_map[day_str]["order_count"] += 1
        daily_map[day_str]["marketplaces"].add(row[1])

    daily_trend = [
        DailySpendingItem(
            date=d,
            total_cost=round(info["total_cost"], 2),
            order_count=info["order_count"],
            marketplaces=sorted(info["marketplaces"]),
        )
        for d, info in sorted(daily_map.items())
    ]

    # 5. Recent Purchases
    recent_res = await db.execute(
        select(PersonalPurchase)
        .where(PersonalPurchase.user_id == user.id)
        .order_by(PersonalPurchase.purchased_at.desc(), PersonalPurchase.created_at.desc())
        .limit(10)
    )
    recent_purchases = list(recent_res.scalars().all())

    return PersonalSpendingAnalytics(
        today_cost=round(today_cost, 2),
        week_cost=round(week_cost, 2),
        month_cost=round(month_cost, 2),
        total_orders=total_orders,
        daily_trend=daily_trend,
        marketplace_breakdown=marketplace_breakdown,
        category_breakdown=category_breakdown,
        recent_purchases=recent_purchases,
    )


@router.get("/transaction-graph", response_model=TransactionGraphResponse)
async def get_transaction_graph(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Computes a real-time directed transaction flow network graph:
    [User Bank Account] -> [Payment Gateway / UPI PSP (Google Pay, PhonePe)] -> [Marketplace / Merchant (Amazon, Flipkart)]
    Calculates routed transaction volumes, order counts, and edge flow amounts.
    """
    res = await db.execute(
        select(PersonalPurchase).where(PersonalPurchase.user_id == user.id)
    )
    purchases = res.scalars().all()

    total_routed = sum(float(p.amount) for p in purchases)

    nodes_map: dict[str, TransactionGraphNode] = {
        "user_bank": TransactionGraphNode(
            id="user_bank",
            label="Your Bank Account (UPI)",
            type="SOURCE",
            subtext="Primary Debit Source",
            total_volume=round(total_routed, 2),
            order_count=len(purchases),
        )
    }

    gateway_volumes: dict[str, float] = {}
    gateway_orders: dict[str, int] = {}
    merchant_volumes: dict[str, float] = {}
    merchant_orders: dict[str, int] = {}
    route_edges: dict[tuple[str, str], dict] = {}

    for p in purchases:
        raw_gw = (p.payment_method or "UPI (Google Pay)").strip()
        gw_id = "gpay" if "google" in raw_gw.lower() else (
            "phonepe" if "phonepe" in raw_gw.lower() else (
                "paytm" if "paytm" in raw_gw.lower() else "other_upi"
            )
        )
        gw_label = "Google Pay UPI" if gw_id == "gpay" else (
            "PhonePe UPI" if gw_id == "phonepe" else (
                "Paytm UPI" if gw_id == "paytm" else raw_gw
            )
        )

        amt = float(p.amount)
        gateway_volumes[gw_id] = gateway_volumes.get(gw_id, 0.0) + amt
        gateway_orders[gw_id] = gateway_orders.get(gw_id, 0) + 1

        if gw_id not in nodes_map:
            nodes_map[gw_id] = TransactionGraphNode(
                id=gw_id,
                label=gw_label,
                type="GATEWAY",
                subtext="UPI Payment Service Provider",
                total_volume=0.0,
                order_count=0,
            )

        mkt_id = f"mkt_{p.marketplace.lower().replace(' ', '_')}"
        merchant_volumes[mkt_id] = merchant_volumes.get(mkt_id, 0.0) + amt
        merchant_orders[mkt_id] = merchant_orders.get(mkt_id, 0) + 1

        if mkt_id not in nodes_map:
            nodes_map[mkt_id] = TransactionGraphNode(
                id=mkt_id,
                label=p.marketplace,
                type="MERCHANT",
                subtext="E-Commerce Merchant",
                total_volume=0.0,
                order_count=0,
            )

        edge_key = (gw_id, mkt_id)
        if edge_key not in route_edges:
            route_edges[edge_key] = {"amount": 0.0, "count": 0}
        route_edges[edge_key]["amount"] += amt
        route_edges[edge_key]["count"] += 1

    for gw_id, vol in gateway_volumes.items():
        if gw_id in nodes_map:
            nodes_map[gw_id].total_volume = round(vol, 2)
            nodes_map[gw_id].order_count = gateway_orders.get(gw_id, 0)

    for mkt_id, vol in merchant_volumes.items():
        if mkt_id in nodes_map:
            nodes_map[mkt_id].total_volume = round(vol, 2)
            nodes_map[mkt_id].order_count = merchant_orders.get(mkt_id, 0)

    edges: list[TransactionGraphEdge] = []
    for gw_id, vol in gateway_volumes.items():
        edges.append(
            TransactionGraphEdge(
                from_node="user_bank",
                to_node=gw_id,
                amount=round(vol, 2),
                order_count=gateway_orders[gw_id],
                status="CONFIRMED",
            )
        )

    for (gw_id, mkt_id), info in route_edges.items():
        edges.append(
            TransactionGraphEdge(
                from_node=gw_id,
                to_node=mkt_id,
                amount=round(info["amount"], 2),
                order_count=info["count"],
                status="CONFIRMED",
            )
        )

    return TransactionGraphResponse(
        nodes=list(nodes_map.values()),
        edges=edges,
        total_routed_volume=round(total_routed, 2),
        currency="INR",
    )


@router.get("/payments-to-others", response_model=OutgoingPaymentsSummaryResponse)
async def get_payments_made_to_others_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Summarizes all payments made by the user to others (marketplaces, direct UPI contacts,
    wholesale suppliers, and retail stores), enriched with scikit-learn KMeans payee clustering,
    Ridge/RandomForest 7d & 30d outflow regression, and IsolationForest anomaly detection.
    """
    summary = await summarize_payments_made_to_others(db=db, user=user)
    return OutgoingPaymentsSummaryResponse(**summary)


@router.get("/store-drilldown", response_model=StoreDrilldownResponse)
async def get_store_drilldown(
    store: str | None = Query(default=None, description="Specific store/merchant name to inspect graphically"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns graphical transaction drill-down for a particular store/merchant/payee:
    - Chronological order bars + running cumulative cost curve
    - Store-specific payment method & category breakdown
    - Directed Store-to-Order flow graph (Bank -> UPI App -> Store -> Individual Orders)
    - EWMA predicted next spend at that store
    """
    drilldown = await get_store_transaction_drilldown(db=db, user=user, store_name=store)
    return StoreDrilldownResponse(**drilldown)


@router.post("/parse-invoice-text", response_model=ParsedInvoiceResponse)
async def parse_invoice_text(
    payload: ParseInvoiceTextRequest,
    user: User = Depends(get_current_user),
):
    """
    Zero-persistence receipt text parser. Parses raw order confirmation text in memory
    to extract order ID, amount, and items for the authenticated user without saving raw text to disk.
    """
    parsed = parse_marketplace_receipt_text(payload.invoice_text)
    return ParsedInvoiceResponse(**parsed)


@router.delete("/{purchase_id}", status_code=status.HTTP_200_OK)
async def delete_purchase(
    purchase_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Deletes a personal purchase strictly verified against user ownership.
    """
    res = await db.execute(
        select(PersonalPurchase).where(
            PersonalPurchase.id == purchase_id,
            PersonalPurchase.user_id == user.id,
        )
    )
    purchase = res.scalar_one_or_none()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase record not found")
    await db.delete(purchase)
    await db.commit()
    return {"status": "success", "deleted_id": str(purchase_id)}

