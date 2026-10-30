import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.cores.database import Base


class BankingConsent(Base):
    """
    Persisted RBI Account Aggregator (AA) consent record.
    Strictly stores masked account references (e.g. XXXX-XXXX-4821) and never
    persists raw account numbers, IFSC codes, netbanking passwords, or MPINs.
    """
    __tablename__ = "banking_consents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    consent_id: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    fip_id: Mapped[str] = mapped_column(String(50), nullable=False)
    fip_name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="APPROVED"
    )  # PENDING, APPROVED, REVOKED, REJECTED
    redirect_url: Mapped[str] = mapped_column(Text, nullable=False)
    purpose_text: Mapped[str] = mapped_column(Text, nullable=False)
    masked_acc: Mapped[str] = mapped_column(String(50), nullable=False)
    fi_types: Mapped[str] = mapped_column(String(100), nullable=False, default='["DEPOSIT"]')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user = relationship("User", backref="banking_consents")


class PaymentWebhookEvent(Base):
    """
    Audit log and idempotency guard for incoming payment gateway webhook events.
    Enforces uniqueness on event_id so replay or duplicate webhooks are safely skipped.
    """
    __tablename__ = "payment_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PROCESSED")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class BankTransaction(Base):
    """
    Persisted outside bank / UPI transaction record imported from a bank CSV/JSON statement,
    Google Pay / PhonePe / Paytm export, or RBI Account Aggregator session.
    Supports both CREDIT (inward income) and DEBIT (personal spending / outward expense).
    """
    __tablename__ = "bank_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    txn_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    date: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="DEBIT")  # CREDIT or DEBIT
    mode: Mapped[str] = mapped_column(String(30), nullable=False, default="UPI")
    app: Mapped[str] = mapped_column(String(50), nullable=False, default="UPI")
    vpa: Mapped[str | None] = mapped_column(String(150), nullable=True)
    narration: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="General")
    counterparty: Mapped[str] = mapped_column(String(150), nullable=False, default="Merchant / Peer")
    masked_acc: Mapped[str] = mapped_column(String(50), nullable=False, default="XXXX-XXXX-4821")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="statement_import")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    user = relationship("User", backref="bank_transactions")

    __table_args__ = (
        UniqueConstraint("user_id", "txn_id", name="uq_bank_transactions_user_txn"),
    )
