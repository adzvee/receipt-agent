"""Builders for fake test data. All vendors and amounts are made up."""

from app.extraction import ExtractedLineItem, ExtractedReceipt


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
