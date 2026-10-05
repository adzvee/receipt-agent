"""Shapes of API responses. Kept separate from database models so the API is a stable contract."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import ReceiptStatus


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal


class ValidationIssueOut(BaseModel):
    code: str
    message: str


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
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

    validation_issues: list[ValidationIssueOut]
    needs_review: bool
