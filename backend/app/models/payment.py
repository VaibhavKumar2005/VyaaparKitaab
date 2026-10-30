import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.cores.database import Base


class Payment(Base):
    """
    Persisted record of an executed payment transaction (UPI, Card, Cash, etc.).
    Uniquely keyed by payment_id (gateway payment ID or internal cash receipt ID).
    Guarantees idempotency and prevents double-counting across /verify and webhooks.
    """
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payment_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    order_id: Mapped[str | None] = mapped_column(
        String(100), index=True, nullable=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), index=True, nullable=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    method: Mapped[str] = mapped_column(String(50), default="UPI", nullable=False)
    vpa: Mapped[str | None] = mapped_column(String(150), nullable=True)
    app: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g. "Google Pay", "PhonePe", "Paytm"
    status: Mapped[str] = mapped_column(String(50), default="captured", nullable=False)
    raw_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    business = relationship("Business", backref="payments")
    invoice = relationship("Invoice", backref="payments")
    customer = relationship("Customer", backref="payments")

    __table_args__ = (
        Index("ix_payments_business_created", "business_id", "created_at"),
        Index("ix_payments_invoice_created", "invoice_id", "created_at"),
    )

