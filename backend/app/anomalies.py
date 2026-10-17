"""Spotting unusual charges by comparing a receipt with past spending.

The rules are deliberately simple so every flag can be explained in one sentence:

- Category: more than 2x the *high end* (90th percentile) of your past purchases in that
  category. Categories mix very different purchases (a $4 coffee and a $45 dinner are both
  "dining"), so comparing with the typical purchase would flag every normal dinner.
- Vendor: more than 2.5x your *median* at that vendor. One vendor's receipts are similar,
  and a median, unlike an average, isn't dragged up by one past splurge.
- Tip: more than 30% of the subtotal.

Charges also have to be at least MIN_EXTRA_AMOUNT above the usual amount: a $12 café order
is "3x" a $4 coffee, but not worth anyone's time to review.
"""

from dataclasses import dataclass
from decimal import Decimal
from statistics import median, quantiles

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FlagKind, Receipt, ReceiptFlag, ReceiptStatus

CATEGORY_MULTIPLIER = Decimal("2")  # x the category's 90th percentile
VENDOR_MULTIPLIER = Decimal("2.5")  # x the vendor's median
# Only compare once there's enough history to know what "usual" is. Categories need more,
# since they mix different kinds of purchases; one vendor's receipts vary much less.
MIN_CATEGORY_HISTORY = 10
MIN_VENDOR_HISTORY = 5
HIGH_TIP_RATIO = Decimal("0.30")
MIN_EXTRA_AMOUNT = Decimal("25")


@dataclass(frozen=True)
class Anomaly:
    code: str
    message: str


def high_end(history: list[Decimal]) -> Decimal:
    """The 90th percentile: 90% of past amounts are at or below it."""
    return Decimal(quantiles(history, n=10, method="inclusive")[-1]).quantize(Decimal("0.01"))


def typical(history: list[Decimal]) -> Decimal:
    return Decimal(median(history)).quantize(Decimal("0.01"))


def is_far_above(total: Decimal, usual: Decimal, multiplier: Decimal) -> bool:
    """True if `total` is both `multiplier` times `usual` and meaningfully more in money."""
    return usual > 0 and total > usual * multiplier and total - usual >= MIN_EXTRA_AMOUNT


def check_tip(tip: Decimal | None, subtotal: Decimal | None) -> Decimal | None:
    """Return the tip as a fraction of the subtotal if it's unusually high, else None."""
    if not tip or not subtotal or subtotal <= 0:
        return None
    ratio = tip / subtotal
    return ratio if ratio > HIGH_TIP_RATIO else None


def detect_anomalies(
    receipt: Receipt, category_history: list[Decimal], vendor_history: list[Decimal]
) -> list[Anomaly]:
    """Pure rule checks; the database lookups happen in `load_history`."""
    if receipt.total is None:
        return []
    anomalies = []

    if receipt.category is not None and len(category_history) >= MIN_CATEGORY_HISTORY:
        usual_high = high_end(category_history)
        if is_far_above(receipt.total, usual_high, CATEGORY_MULTIPLIER):
            anomalies.append(
                Anomaly(
                    "high_for_category",
                    f"{receipt.total} is more than {CATEGORY_MULTIPLIER}x the high end of your "
                    f"usual {receipt.category.value} purchases ({usual_high}).",
                )
            )

    if len(vendor_history) >= MIN_VENDOR_HISTORY:
        usual = typical(vendor_history)
        if is_far_above(receipt.total, usual, VENDOR_MULTIPLIER):
            anomalies.append(
                Anomaly(
                    "high_for_vendor",
                    f"{receipt.total} is more than {VENDOR_MULTIPLIER}x what you usually spend "
                    f"at {receipt.vendor} ({usual}).",
                )
            )

    ratio = check_tip(receipt.tip, receipt.subtotal)
    if ratio is not None:
        anomalies.append(
            Anomaly("high_tip", f"The tip ({receipt.tip}) is {ratio:.0%} of the subtotal.")
        )

    return anomalies


def load_history(db: Session, receipt: Receipt) -> tuple[list[Decimal], list[Decimal]]:
    """Totals of other receipts in the same category, and from the same vendor."""
    base = select(Receipt.total).where(
        Receipt.user_id == receipt.user_id,
        Receipt.id != receipt.id,
        Receipt.status == ReceiptStatus.EXTRACTED,
        Receipt.total.is_not(None),
        Receipt.currency.is_not_distinct_from(receipt.currency),  # don't compare $ with €
    )
    category_history = (
        list(db.scalars(base.where(Receipt.category == receipt.category)))
        if receipt.category is not None
        else []
    )
    vendor_history = (
        list(db.scalars(base.where(Receipt.vendor_key == receipt.vendor_key)))
        if receipt.vendor_key
        else []
    )
    return category_history, vendor_history


def find_anomaly_flags(db: Session, receipt: Receipt) -> list[ReceiptFlag]:
    anomalies = detect_anomalies(receipt, *load_history(db, receipt))
    return [ReceiptFlag(kind=FlagKind.ANOMALY, code=a.code, message=a.message) for a in anomalies]
