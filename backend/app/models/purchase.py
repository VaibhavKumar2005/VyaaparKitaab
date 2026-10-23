import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.cores.database import Base
from app.services.encryption import EncryptedString


class PersonalPurchase(Base):
    """
    Closed & Encrypted Personal Purchase Model.
    All marketplace purchases (Amazon, Flipkart, etc.) and private item details
    are encrypted at rest (AES-128 Fernet). Only the authenticated user can access their records.
    """
    __tablename__ = "personal_purchases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    marketplace: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="Shopping", index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Encrypted fields at rest (stored as ciphertext enc_v1:...)
    order_id: Mapped[str] = mapped_column(EncryptedString(512), nullable=False)
    order_id_bidx: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    items_note: Mapped[str | None] = mapped_column(EncryptedString(1024), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User", backref="personal_purchases")

    __table_args__ = (
        UniqueConstraint("user_id", "marketplace", "order_id_bidx", name="uq_user_mkt_order_bidx"),
    )

