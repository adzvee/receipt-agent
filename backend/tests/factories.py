"""Builders for fake test data. All vendors and amounts are made up."""

import hashlib
from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.categorization import CategoryDecision
from app.extraction import ExtractedLineItem, ExtractedReceipt
from app.models import (
    Category,
    CategorySource,
    FlagKind,
    LineItem,
    Receipt,
    ReceiptFlag,
    ReceiptStatus,
)
from app.vendors import normalize_vendor


def make_extracted_receipt(**overrides) -> ExtractedReceipt:
    """A small, internally consistent café receipt: 4.50 + 3.25 = 7.75, + 0.62 tax = 8.37."""
    fields = {
        "vendor": "Corner Cafe",
        "purchase_date": "2026-09-14",
        "currency": "USD",
        "line_items": [
            ExtractedLineItem(description="Latte", quantity=1, unit_price=4.50, amount=4.50),
            ExtractedLineItem(description="Croissant", quantity=1, unit_price=3.25, amount=3.25),
        ],
        "subtotal": 7.75,
        "tax": 0.62,
        "tip": None,
        "total": 8.37,
        "payment_method": "Visa ending 4242",
    }
    fields.update(overrides)
    return ExtractedReceipt(**fields)


def make_category_decision(category: Category = Category.DINING) -> CategoryDecision:
    return CategoryDecision(category=category, reason="It's a café.")


def add_receipt(
    db: Session,
    *,
    vendor: str = "Corner Cafe",
    total: str = "8.37",
    purchase_date: date = date(2026, 9, 1),
    category: Category | None = Category.DINING,
    category_source: CategorySource | None = CategorySource.LLM,
    currency: str | None = "USD",
    status: ReceiptStatus = ReceiptStatus.EXTRACTED,
    line_items: list[tuple[str, str]] = (),
    flags: list[tuple[FlagKind, str]] = (),
) -> Receipt:
    """Insert an already-processed receipt directly, to set up data for a test.

    `line_items` are (description, amount) pairs; `flags` are (kind, code) pairs.
    """
    receipt = Receipt(
        original_filename="seed.png",
        content_type="image/png",
        file_key=f"receipts/{uuid4().hex}.png",
        file_sha256=hashlib.sha256(uuid4().bytes).hexdigest(),
        status=status,
        vendor=vendor,
        vendor_key=normalize_vendor(vendor),
        purchase_date=purchase_date,
        currency=currency,
        total=Decimal(total),
        category=category,
        category_source=category_source,
        line_items=[
            LineItem(position=i, description=description, amount=Decimal(amount))
            for i, (description, amount) in enumerate(line_items)
        ],
        flags=[ReceiptFlag(kind=kind, code=code, message=code) for kind, code in flags],
    )
    db.add(receipt)
    db.flush()
    return receipt
