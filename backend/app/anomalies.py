"""Spotting unusual charges by comparing a receipt with past spending.

The rules are deliberately simple so every flag can be explained in one sentence.
They compare against the *median* of past totals, which a single huge purchase can't skew
the way it would skew an average.
"""

from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FlagKind, Receipt, ReceiptFlag, ReceiptStatus

# Flag a total this many times the usual amount...
CATEGORY_MULTIPLIER = Decimal("3")
VENDOR_MULTIPLIER = Decimal("2.5")
# ...but only once there's enough history to know what "usual" is.
MIN_CATEGORY_HISTORY = 5
MIN_VENDOR_HISTORY = 3
# Tips above this share of the pre-tip amount are flagged.
HIGH_TIP_RATIO = Decimal("0.30")


@dataclass(frozen=True)
class Anomaly:
    code: str
    message: str


def check_against_history(
    total: Decimal, history: list[Decimal], multiplier: Decimal, min_history: int
) -> Decimal | None:
    """Return the typical (median) amount if `total` is unusually high, else None."""
    if len(history) < min_history:
        return None
    typical = Decimal(median(history))
    return typical if typical > 0 and total > typical * multiplier else None


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

    typical = check_against_history(
        receipt.total, category_history, CATEGORY_MULTIPLIER, MIN_CATEGORY_HISTORY
    )
    if typical is not None and receipt.category is not None:
        anomalies.append(
            Anomaly(
                "high_for_category",
                f"{receipt.total} is more than {CATEGORY_MULTIPLIER}x your typical "
                f"{receipt.category.value} purchase ({typical:.2f}).",
            )
        )

    typical = check_against_history(
        receipt.total, vendor_history, VENDOR_MULTIPLIER, MIN_VENDOR_HISTORY
    )
    if typical is not None:
        anomalies.append(
            Anomaly(
                "high_for_vendor",
                f"{receipt.total} is more than {VENDOR_MULTIPLIER}x what you usually spend "
                f"at {receipt.vendor} ({typical:.2f}).",
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
