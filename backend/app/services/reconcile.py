"""Match real bank/UPI credits against open store invoices and settle atomically."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.money import ZERO, money_to_float, to_money
from app.models.banking_consent import BankTransaction
from app.models.business import Business, Customer
from app.models.payment import Payment
from app.models.transaction import Invoice
from app.models.user import User
from app.services.payment_recorder import OverpaymentError, record_payment


def _recon_payment_id(user_id: UUID, txn_id: str) -> str:
    return f"bank_recon:{str(user_id)[:8]}:{txn_id}"[:85]


def _customer_tokens(name: str | None) -> list[str]:
    if not name:
        return []
    return [tok for tok in name.lower().split() if len(tok) >= 3]


async def find_reconciliation_suggestions(
    db: AsyncSession,
    user: User,
) -> list[dict[str, Any]]:
    """Suggests high-confidence pairings between imported CREDIT rows and unpaid store SALE invoices."""
    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    open_invoices = (
        await db.execute(
            select(Invoice)
            .where(
                Invoice.business_id.in_(owned_businesses),
                Invoice.type == "SALE",
                Invoice.status == "CONFIRMED",
                Invoice.total_amount > Invoice.paid_amount,
            )
            .order_by(Invoice.created_at.desc())
        )
    ).scalars().all()
    if not open_invoices:
        return []

    cust_ids = {inv.customer_id for inv in open_invoices if inv.customer_id}
    customers_map: dict[UUID, Customer] = {}
    if cust_ids:
        cust_rows = (await db.execute(select(Customer).where(Customer.id.in_(cust_ids)))).scalars().all()
        customers_map = {c.id: c for c in cust_rows}

    credits = (
        await db.execute(
            select(BankTransaction)
            .where(BankTransaction.user_id == user.id, BankTransaction.type == "CREDIT")
            .order_by(BankTransaction.timestamp.desc())
            .limit(100)
        )
    ).scalars().all()
    if not credits:
        return []

    candidate_pids = [_recon_payment_id(user.id, tx.txn_id) for tx in credits]
    settled_rows = (
        await db.execute(select(Payment.payment_id).where(Payment.payment_id.in_(candidate_pids)))
    ).scalars().all()
    already_reconciled = set(settled_rows)

    suggestions: list[dict[str, Any]] = []
    for tx in credits:
        if _recon_payment_id(user.id, tx.txn_id) in already_reconciled:
            continue
        tx_amount_dec = to_money(tx.amount)
        haystack = f"{tx.narration or ''} {tx.counterparty or ''}".lower()

        best_match: tuple[int, dict[str, Any]] | None = None
        for inv in open_invoices:
            due_dec = max(to_money(inv.total_amount) - to_money(inv.paid_amount or ZERO), ZERO)
            if due_dec <= ZERO or tx_amount_dec > due_dec:
                continue

            cust = customers_map.get(inv.customer_id) if inv.customer_id else None
            inv_num_lower = (inv.invoice_number or "").lower()
            has_inv_ref = bool(inv_num_lower and inv_num_lower in haystack)
            amount_diff = abs(tx_amount_dec - due_dec)
            amount_exact = amount_diff <= Decimal("1.00")
            tokens = _customer_tokens(cust.name if cust else None)
            has_cust_match = any(tok in haystack for tok in tokens)

            if not (has_inv_ref or amount_exact):
                continue

            score = 0
            reasons: list[str] = []
            if has_inv_ref:
                score += 60
                reasons.append(f"Narration references {inv.invoice_number}")
            if amount_exact:
                score += 40
                reasons.append(f"Exact amount match (₹{due_dec:.2f})")
            if has_cust_match and cust:
                score += 20
                reasons.append(f"Payer matches {cust.name}")

            confidence = "HIGH" if score >= 60 else "MEDIUM"
            candidate = {
                "txn_id": tx.txn_id,
                "txn_amount": money_to_float(tx_amount_dec),
                "txn_date": tx.date,
                "txn_app": tx.app,
                "counterparty": tx.counterparty,
                "narration": tx.narration,
                "invoice_id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "customer_name": cust.name if cust else "Walk-in Customer",
                "due_amount": money_to_float(due_dec),
                "confidence": confidence,
                "match_reason": " · ".join(reasons),
            }
            if best_match is None or score > best_match[0]:
                best_match = (score, candidate)

        if best_match is not None:
            suggestions.append(best_match[1])

    return suggestions


async def apply_bank_reconciliation(
    db: AsyncSession,
    user: User,
    *,
    txn_id: str,
    invoice_id: UUID,
) -> dict[str, Any]:
    """Marks an owned open invoice paid using a verified bank/UPI CREDIT row via single-writer record_payment."""
    tx = (
        await db.execute(
            select(BankTransaction).where(
                BankTransaction.user_id == user.id,
                BankTransaction.txn_id == txn_id,
                BankTransaction.type == "CREDIT",
            )
        )
    ).scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="Bank credit transaction not found")

    owned_businesses = select(Business.id).where(Business.owner_id == user.id)
    invoice = (
        await db.execute(
            select(Invoice)
            .where(
                Invoice.id == invoice_id,
                Invoice.business_id.in_(owned_businesses),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=404, detail="Open store invoice not found")

    due_dec = max(to_money(invoice.total_amount) - to_money(invoice.paid_amount or ZERO), ZERO)
    if due_dec <= ZERO:
        raise HTTPException(status_code=400, detail="Invoice is already fully settled")

    recon_pid = _recon_payment_id(user.id, tx.txn_id)
    already_recorded = (
        await db.execute(select(Payment.id).where(Payment.payment_id == recon_pid))
    ).scalar_one_or_none()
    if already_recorded is not None:
        return {
            "reconciled": False,
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "invoice_status": invoice.status,
            "paid_amount": money_to_float(invoice.paid_amount or ZERO),
            "message": "Payment already recorded (duplicate skipped)",
        }

    tx_amt = to_money(tx.amount)
    if tx_amt <= ZERO:
        raise HTTPException(status_code=400, detail="Bank credit amount must be positive")
    if tx_amt > due_dec:
        await db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Overpayment rejected: bank credit {tx_amt} exceeds invoice balance due {due_dec}",
        )

    try:
        rec = await record_payment(
            db,
            {
                "payment_id": recon_pid,
                "order_id": f"recon_{tx.txn_id[:40]}",
                "invoice_id": invoice.id,
                "business_id": invoice.business_id,
                "customer_id": invoice.customer_id,
                "amount": tx_amt,
                "currency": "INR",
                "method": tx.mode or "UPI",
                "vpa": tx.vpa,
                "status": "captured",
                "raw_response": {"reconciled_txn_id": tx.txn_id, "source": tx.source},
            },
        )
    except OverpaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "reconciled": rec["inserted"],
        "invoice_id": str(invoice.id),
        "invoice_number": invoice.invoice_number,
        "invoice_status": rec["invoice_status"],
        "paid_amount": rec["paid_amount"],
        "message": rec["message"],
    }
