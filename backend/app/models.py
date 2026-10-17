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


def str_enum(enum_class: type[enum.StrEnum]) -> Enum:
    """Store a Python enum as a plain string column (easier to change than a Postgres enum)."""
    return Enum(
        enum_class,
        native_enum=False,
        length=30,
        values_callable=lambda e: [m.value for m in e],
    )


class ReceiptStatus(enum.StrEnum):
    EXTRACTED = "extracted"
    FAILED = "failed"  # the LLM call failed; the file is saved and can be retried


class ReceiptSource(enum.StrEnum):
    UPLOAD = "upload"
    EMAIL = "email"


class Category(enum.StrEnum):
    GROCERIES = "groceries"
    DINING = "dining"
    TRANSPORTATION = "transportation"
    TRAVEL = "travel"
    SHOPPING = "shopping"
    UTILITIES = "utilities"
    HEALTH = "health"
    ENTERTAINMENT = "entertainment"
    SUBSCRIPTIONS = "subscriptions"
    EDUCATION = "education"
    OFFICE = "office"
    OTHER = "other"


class CategorySource(enum.StrEnum):
    LLM = "llm"
    VENDOR_HISTORY = "vendor_history"  # copied from an earlier receipt from the same vendor
    USER = "user"


class FlagKind(enum.StrEnum):
    EXTRACTION = "extraction"  # the LLM couldn't read the receipt
    VALIDATION = "validation"  # the numbers don't add up, or a field is missing
    DUPLICATE = "duplicate"
    ANOMALY = "anomaly"  # an unusual charge


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lowercase
    password_hash: Mapped[str] = mapped_column(String(255))
    # Private part of the user's forwarding address: <inbox>+<token>@<domain>.
    inbound_token: Mapped[str] = mapped_column(String(64), unique=True)
    # Demo accounts are created by "Try demo", expire, and have a cap on AI requests.
    is_demo: Mapped[bool] = mapped_column(default=False, server_default="false")
    llm_requests_used: Mapped[int] = mapped_column(default=0, server_default="0")


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Where it came from
    source: Mapped[ReceiptSource] = mapped_column(
        str_enum(ReceiptSource), default=ReceiptSource.UPLOAD, server_default="upload"
    )
    inbound_email_id: Mapped[int | None] = mapped_column(
        ForeignKey("inbound_emails.id", ondelete="SET NULL"), index=True
    )

    # The uploaded file
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    file_key: Mapped[str] = mapped_column(String(255), unique=True)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)

    # Extraction outcome
    status: Mapped[ReceiptStatus] = mapped_column(str_enum(ReceiptStatus))
    extraction_error: Mapped[str | None] = mapped_column(Text)
    raw_extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Extracted fields
    vendor: Mapped[str | None] = mapped_column(String(255))
    vendor_key: Mapped[str | None] = mapped_column(String(255), index=True)  # normalized vendor
    purchase_date: Mapped[date | None] = mapped_column(Date, index=True)
    currency: Mapped[str | None] = mapped_column(String(3))
    subtotal: Mapped[Decimal | None] = mapped_column(Money)
    tax: Mapped[Decimal | None] = mapped_column(Money)
    tip: Mapped[Decimal | None] = mapped_column(Money)
    total: Mapped[Decimal | None] = mapped_column(Money)
    payment_method: Mapped[str | None] = mapped_column(String(100))

    # Categorization
    category: Mapped[Category | None] = mapped_column(str_enum(Category), index=True)
    category_source: Mapped[CategorySource | None] = mapped_column(str_enum(CategorySource))
    category_reason: Mapped[str | None] = mapped_column(Text)

    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="LineItem.position",
        lazy="selectin",
    )
    flags: Mapped[list["ReceiptFlag"]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="ReceiptFlag.id",
        lazy="selectin",
        foreign_keys="ReceiptFlag.receipt_id",
    )

    @property
    def needs_review(self) -> bool:
        return any(flag.dismissed_at is None for flag in self.flags)


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


class ReceiptFlag(Base):
    """Something about a receipt that a person should look at. Dismissing it clears the flag."""

    __tablename__ = "receipt_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        ForeignKey("receipts.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[FlagKind] = mapped_column(str_enum(FlagKind))
    code: Mapped[str] = mapped_column(String(50))  # e.g. "total_mismatch", "likely_duplicate"
    message: Mapped[str] = mapped_column(Text)
    # For duplicates: the earlier receipt this one matches.
    related_receipt_id: Mapped[int | None] = mapped_column(
        ForeignKey("receipts.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    receipt: Mapped[Receipt] = relationship(back_populates="flags", foreign_keys=[receipt_id])


class InboundEmail(Base):
    """An email forwarded to the app, and whether it turned out to be a receipt."""

    __tablename__ = "inbound_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Postmark's id for the email. Unique, so a webhook that's re-sent is processed once.
    message_id: Mapped[str] = mapped_column(String(255), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    from_email: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(Text)
    is_receipt: Mapped[bool]
    classification_reason: Mapped[str] = mapped_column(Text)

    receipts: Mapped[list[Receipt]] = relationship(order_by="Receipt.id")
