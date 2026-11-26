"""Canonical unified transaction ledger & customer notification models."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.cores.database import Base


class UnifiedTransaction(Base):
    """
    Canonical normalized ledger connecting both sides of the two-sided MSME platform:
      - Store (B) side: store sales, supplier purchases, invoice settlements, discounts given
      - Customer (C) side: retail bills, discounts saved, personal marketplace/OCR purchases,
        statement/PDF imports, Account Aggregator feeds, and optional UPI bridge connectors.

    Uniquely keyed by `(source_type, source_ref_id)` for idempotent cross-channel writes.
    """

    __tablename__ = "unified_transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )

    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_ref_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)

    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="DEBIT")
    side: Mapped[str] = mapped_column(String(16), nullable=False, default="CUSTOMER")

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="INR")

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="RECORDED")
    channel: Mapped[str] = mapped_column(String(40), nullable=False, default="UPI")
    app: Mapped[str | None] = mapped_column(String(50), nullable=True)

    counterparty: Mapped[str] = mapped_column(String(180), nullable=False, default="Merchant")
    narration: Mapped[str] = mapped_column(Text, nullable=False, default="")

    category: Mapped[str] = mapped_column(String(80), nullable=False, default="Other", index=True)
    subcategory: Mapped[str] = mapped_column(String(80), nullable=False, default="General", index=True)
    classification_source: Mapped[str] = mapped_column(String(32), nullable=False, default="rule")

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", backref="unified_transactions")
    business = relationship("Business", backref="unified_transactions")
    customer = relationship("Customer", backref="unified_transactions")
    invoice = relationship("Invoice", backref="unified_transactions")

    __table_args__ = (
        UniqueConstraint("source_type", "source_ref_id", name="uq_unified_txn_source_ref"),
        Index("ix_unified_txn_user_occurred", "user_id", "occurred_at"),
        Index("ix_unified_txn_biz_occurred", "business_id", "occurred_at"),
        Index("ix_unified_txn_cust_occurred", "customer_id", "occurred_at"),
    )


class CustomerNotification(Base):
    """
    Persistent purchase & payment receipt notifications pushed to linked customers
    whenever a store confirms/updates a bill or captures a payment.
    """

    __tablename__ = "customer_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )

    event_key: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, default="purchase.recorded")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="Other")
    subcategory: Mapped[str] = mapped_column(String(80), nullable=False, default="General")
    payment_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )
