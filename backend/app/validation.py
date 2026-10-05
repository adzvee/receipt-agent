"""Sanity checks on extracted receipt data. Any issue flags the receipt for human review."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.extraction import ExtractedReceipt, money, parse_date

# Allow a couple of cents of rounding difference between printed and computed totals.
TOLERANCE = Decimal("0.02")


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


def validate_receipt(receipt: ExtractedReceipt, today: date) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not receipt.vendor:
        issues.append(ValidationIssue("missing_vendor", "No vendor name was found."))

    purchase_date = parse_date(receipt.purchase_date)
    if receipt.purchase_date is None:
        issues.append(ValidationIssue("missing_date", "No purchase date was found."))
    elif purchase_date is None:
        issues.append(
            ValidationIssue("invalid_date", f"'{receipt.purchase_date}' is not a valid date.")
        )
    elif purchase_date > today:
        issues.append(ValidationIssue("future_date", f"The date {purchase_date} is in the future."))

    total = money(receipt.total)
    if total is None:
        issues.append(ValidationIssue("missing_total", "No total was found."))

    items_sum = sum((money(item.amount) for item in receipt.line_items), Decimal("0"))
    subtotal = money(receipt.subtotal)

    if receipt.line_items and subtotal is not None and abs(items_sum - subtotal) > TOLERANCE:
        issues.append(
            ValidationIssue(
                "line_items_mismatch",
                f"Line items add up to {items_sum} but the subtotal is {subtotal}.",
            )
        )

    base = subtotal if subtotal is not None else (items_sum if receipt.line_items else None)
    if total is not None and base is not None:
        tax = money(receipt.tax) or Decimal("0")
        tip = money(receipt.tip) or Decimal("0")
        # Accept both "tax added on top" and "tax already included in prices" receipts.
        candidates = {base + tax + tip, base + tip}
        if all(abs(total - expected) > TOLERANCE for expected in candidates):
            issues.append(
                ValidationIssue(
                    "total_mismatch",
                    f"Subtotal {base} + tax {tax} + tip {tip} does not equal the total {total}.",
                )
            )

    return issues
