"""Database tables, as SQLAlchemy models."""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(12, 2)


class ReceiptStatus(enum.StrEnum):
    EXTRACTED = "extracted"
    FAILED = "failed"  # the LLM call failed; the file is saved and can be retried


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # The uploaded file
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    file_key: Mapped[str] = mapped_column(String(255), unique=True)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)

    # Extraction outcome
    status: Mapped[ReceiptStatus] = mapped_column(
        Enum(
            ReceiptStatus,
            native_enum=False,  # stored as a plain string column; easier to migrate
            length=20,
            values_callable=lambda e: [m.value for m in e],
        )
    )
    extraction_error: Mapped[str | None] = mapped_column(Text)
    raw_extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Extracted fields
    vendor: Mapped[str | None] = mapped_column(String(255))
    purchase_date: Mapped[date | None] = mapped_column(Date, index=True)
    currency: Mapped[str | None] = mapped_column(String(3))
    subtotal: Mapped[Decimal | None] = mapped_column(Money)
    tax: Mapped[Decimal | None] = mapped_column(Money)
    tip: Mapped[Decimal | None] = mapped_column(Money)
    total: Mapped[Decimal | None] = mapped_column(Money)
    payment_method: Mapped[str | None] = mapped_column(String(100))

    # Validation
    validation_issues: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    needs_review: Mapped[bool] = mapped_column(default=False)

    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="LineItem.position",
        lazy="selectin",
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]  # order on the receipt, starting at 0
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    amount: Mapped[Decimal] = mapped_column(Money)

    receipt: Mapped[Receipt] = relationship(back_populates="line_items")
