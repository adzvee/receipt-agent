"""Shapes of API requests and responses.

Kept separate from the database models so the API stays a stable contract.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import Category, CategorySource, FlagKind, ReceiptSource, ReceiptStatus


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: FlagKind
    code: str
    message: str
    related_receipt_id: int | None
    dismissed_at: datetime | None


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    source: ReceiptSource
    original_filename: str
    content_type: str
    status: ReceiptStatus
    extraction_error: str | None

    vendor: str | None
    purchase_date: date | None
    currency: str | None
    subtotal: Decimal | None
    tax: Decimal | None
    tip: Decimal | None
    total: Decimal | None
    payment_method: str | None
    line_items: list[LineItemOut]

    category: Category | None
    category_source: CategorySource | None
    category_reason: str | None

    flags: list[FlagOut]
    needs_review: bool


class ReceiptUpdate(BaseModel):
    category: Category
