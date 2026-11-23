"""Store-to-customer receipt & payment notification service."""
from __future__ import annotations

import asyncio
import logging
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.cores.config import settings
from app.models.business import Business, Customer
from app.models.transaction import Invoice
from app.models.unified_transaction import CustomerNotification
from app.models.user import User
from app.services.customer_link import linked_customer_ids
from app.services.event_bus import publish_event
from app.services.otp import ALLOWED_SMTP_HOSTS

logger = logging.getLogger(__name__)


async def resolve_linked_customer_user(
    db: AsyncSession,
    customer_id: UUID | None,
) -> User | None:
    """
    Resolves the verified `User` account linked to a store's `Customer` row.
    Matching requires `phone_verified == True` or `email_verified == True`,
    matching the strict authorization rules in `customer_link.py`.
    """
    if customer_id is None or not isinstance(db, AsyncSession):
        return None

    # Handle case where Invoice.customer_id directly holds a User UUID
    direct_user = (
        await db.execute(select(User).where(User.id == customer_id))
    ).scalar_one_or_none()
    if isinstance(direct_user, User):
        return direct_user

    cust = (
        await db.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if not isinstance(cust, Customer):
        return None

    candidates: list[Any] = []
    if cust.phone:
        raw_phone = cust.phone.strip()
        digits = "".join(ch for ch in raw_phone if ch.isdigit())
        variants = {raw_phone}
        if len(digits) >= 10:
            last10 = digits[-10:]
            variants.update({last10, f"+91{last10}", f"91{last10}"})
        candidates.append((User.phone_verified.is_(True)) & (User.phone.in_(list(variants))))

    if cust.email:
        candidates.append(
            (User.email_verified.is_(True)) & (func.lower(User.email) == cust.email.strip().lower())
        )

    if not candidates:
        return None

    user_res = await db.execute(select(User).where(or_(*candidates)))
    return user_res.scalars().first()


def _send_receipt_email_sync(
    recipient_email: str,
    store_name: str,
    invoice_number: str,
    amount: float,
    discount_amount: float,
    category: str,
    subcategory: str,
    payment_channel: str,
) -> None:
    host = settings.SMTP_HOST.strip().lower()
    if host not in ALLOWED_SMTP_HOSTS:
        return
    msg = EmailMessage()
    sender = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
    msg["Subject"] = f"Receipt {invoice_number} from {store_name} - ₹{amount:,.2f}"
    msg["From"] = f"VyaparKitaab Receipts <{sender}>"
    msg["To"] = recipient_email
    msg.set_content(
        f"Thank you for shopping with {store_name}.\n"
        f"Invoice: {invoice_number}\n"
        f"Amount: INR {amount:,.2f} (Discount saved: INR {discount_amount:,.2f})\n"
        f"Category: {category} > {subcategory}\n"
        f"Channel: {payment_channel}\n"
    )
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


async def notify_customer_purchase(
    db: AsyncSession,
    *,
    invoice: Invoice,
    store_name: str,
    category: str,
    subcategory: str,
    linked_user: User | None = None,
    payment_channel: str | None = None,
    app_name: str | None = None,
    event_type: str = "purchase.recorded",
    event_key: str | None = None,
    commit: bool = False,
) -> CustomerNotification | None:
    """
    Persists an idempotent customer receipt notification and emits a real-time SSE event
    for both the Store Dashboard (`store_id`) and Customer Passbook (`customer_id`).
    """
    if linked_user is None and invoice.customer_id is not None:
        linked_user = await resolve_linked_customer_user(db, invoice.customer_id)

    channel_label = app_name or payment_channel or invoice.payment_method or "UPI"
    total_amt = round(float(invoice.total_amount or 0.0), 2)
    paid_amt = round(float(invoice.paid_amount or 0.0), 2)
    disc_amt = round(float(invoice.discount_amount or 0.0), 2)
    inv_status = (invoice.status or "CONFIRMED").upper()

    title = (
        f"Payment Confirmed: ₹{paid_amt:,.2f} at {store_name}"
        if inv_status == "PAID"
        else f"New Store Bill: ₹{total_amt:,.2f} at {store_name}"
    )
    saved_note = f" You saved ₹{disc_amt:,.2f} in discounts." if disc_amt > 0 else ""
    message = (
        f"Bill {invoice.invoice_number} ({category} > {subcategory}) is {inv_status} "
        f"via {channel_label}.{saved_note}"
    )

    resolved_key = event_key or f"{event_type}:{invoice.id}:{inv_status}"
    target_customer_user_id = linked_user.id if linked_user is not None else None

    stmt = (
        insert(CustomerNotification)
        .values(
            user_id=target_customer_user_id,
            customer_id=invoice.customer_id,
            business_id=invoice.business_id,
            invoice_id=invoice.id,
            event_key=resolved_key,
            event_type=event_type,
            title=title[:200],
            message=message,
            amount=total_amt,
            discount_amount=disc_amt,
            category=category,
            subcategory=subcategory,
            payment_channel=channel_label[:50],
            is_read=False,
        )
        .on_conflict_do_nothing(index_elements=[CustomerNotification.event_key])
        .returning(CustomerNotification)
    )
    res = await db.execute(stmt)
    notif = res.scalar_one_or_none()
    if commit:
        await db.commit()
    else:
        await db.flush()

    if notif is not None:
        sse_customer_target = (
            str(target_customer_user_id)
            if target_customer_user_id is not None
            else (str(invoice.customer_id) if invoice.customer_id else None)
        )
        await publish_event(
            event_type=event_type,
            data={
                "event": event_type,
                "notification_id": str(notif.id),
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "store_id": str(invoice.business_id),
                "store_name": store_name,
                "customer_id": sse_customer_target,
                "amount": total_amt,
                "paid_amount": paid_amt,
                "discount_amount": disc_amt,
                "category": category,
                "subcategory": subcategory,
                "channel": channel_label,
                "status": inv_status,
                "title": title,
                "message": message,
                "timestamp": datetime.now(UTC).isoformat(),
            },
            store_id=str(invoice.business_id),
            customer_id=sse_customer_target,
            event_id=f"notif_{resolved_key}",
        )

        # Optional SMTP receipt dispatch only when explicitly configured and verified
        if (
            linked_user is not None
            and getattr(linked_user, "email_verified", False) is True
            and linked_user.email
            and not linked_user.email.endswith(".local")
            and settings.SMTP_USER
            and settings.SMTP_PASSWORD
        ):
            try:
                await asyncio.to_thread(
                    _send_receipt_email_sync,
                    linked_user.email,
                    store_name,
                    invoice.invoice_number,
                    total_amt,
                    disc_amt,
                    category,
                    subcategory,
                    channel_label,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Optional email receipt dispatch skipped for %s: %s", invoice.invoice_number, exc)

    return notif


def _notification_access_clause(user: User):
    return or_(
        CustomerNotification.user_id == user.id,
        CustomerNotification.customer_id == user.id,
        CustomerNotification.customer_id.in_(linked_customer_ids(user)),
    )


async def list_customer_notifications(
    db: AsyncSession,
    user: User,
    limit: int = 30,
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(CustomerNotification, Business.name)
            .outerjoin(Business, Business.id == CustomerNotification.business_id)
            .where(_notification_access_clause(user))
            .order_by(desc(CustomerNotification.created_at))
            .limit(limit)
        )
    ).all()

    return [
        {
            "id": str(n.id),
            "event_type": n.event_type,
            "invoice_id": str(n.invoice_id) if n.invoice_id else None,
            "business_id": str(n.business_id) if n.business_id else None,
            "store_name": b_name or "VyaparKitaab Store",
            "title": n.title,
            "message": n.message,
            "amount": round(float(n.amount), 2),
            "discount_amount": round(float(n.discount_amount), 2),
            "category": n.category,
            "subcategory": n.subcategory,
            "payment_channel": n.payment_channel,
            "is_read": bool(n.is_read),
            "created_at": n.created_at.isoformat() if n.created_at else "",
        }
        for n, b_name in rows
    ]


async def mark_notifications_read(
    db: AsyncSession,
    user: User,
    notification_id: UUID | None = None,
) -> int:
    stmt = (
        update(CustomerNotification)
        .where(_notification_access_clause(user), CustomerNotification.is_read.is_(False))
        .values(is_read=True)
    )
    if notification_id is not None:
        stmt = stmt.where(CustomerNotification.id == notification_id)
    res = await db.execute(stmt)
    await db.commit()
    return int(res.rowcount or 0)
