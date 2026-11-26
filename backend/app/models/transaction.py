import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.cores.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    business_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("businesses.id"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(Enum("SALE", "PURCHASE", name="invoice_type"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("DRAFT", "CONFIRMED", "PAID", "CANCELLED", name="invoice_status"),
        default="DRAFT",
        nullable=False,
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    payment_method: Mapped[str | None] = mapped_column(
        Enum("CASH", "UPI", "CARD", "CREDIT", name="payment_method"), nullable=True
    )
    pending_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pending_order_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    invoice = relationship("Invoice", back_populates="items")


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(
        Enum("TRANSACTION", "LOGIN", "AA_CONSENT", name="otp_purpose"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)