"""Spotting receipts that were already uploaded."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FlagKind, Receipt, ReceiptFlag
from app.vendors import vendors_match


def find_duplicate_flags(db: Session, receipt: Receipt) -> list[ReceiptFlag]:
    """Flag the receipt if an earlier one is the same file, or the same purchase.

    "Same purchase" (same vendor, date, and total) catches e.g. a photo of a receipt
    and the emailed PDF of the same receipt.
    """
    earlier = (
        select(Receipt)
        .where(Receipt.user_id == receipt.user_id, Receipt.id != receipt.id)
        .order_by(Receipt.id)
    )

    same_file = db.scalars(earlier.where(Receipt.file_sha256 == receipt.file_sha256)).first()
    if same_file is not None:
        return [
            ReceiptFlag(
                kind=FlagKind.DUPLICATE,
                code="duplicate_file",
                message=f"This is the same file as receipt #{same_file.id}.",
                related_receipt_id=same_file.id,
            )
        ]

    if receipt.purchase_date is None or receipt.total is None:
        return []
    candidates = db.scalars(
        earlier.where(
            Receipt.purchase_date == receipt.purchase_date, Receipt.total == receipt.total
        )
    )
    for candidate in candidates:
        if vendors_match(candidate.vendor, receipt.vendor):
            return [
                ReceiptFlag(
                    kind=FlagKind.DUPLICATE,
                    code="likely_duplicate",
                    message=(
                        f"Same vendor, date, and total as receipt #{candidate.id}. "
                        "Dismiss this flag if it's a separate purchase."
                    ),
                    related_receipt_id=candidate.id,
                )
            ]
    return []
