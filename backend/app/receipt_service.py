"""The upload pipeline.

store → extract → validate → categorize → check for duplicates and anomalies → save
"""

import hashlib
from datetime import date
from uuid import uuid4

from sqlalchemy.orm import Session

from app.anomalies import find_anomaly_flags
from app.categorization import assign_category
from app.duplicates import find_duplicate_flags
from app.extraction import ExtractedReceipt, extract_receipt, money, parse_date, quantity
from app.file_types import FILE_EXTENSIONS
from app.llm import LLMClient, LLMError
from app.models import (
    FlagKind,
    LineItem,
    Receipt,
    ReceiptFlag,
    ReceiptSource,
    ReceiptStatus,
)
from app.redaction import redact_extraction
from app.storage import FileStorage
from app.validation import validate_receipt
from app.vendors import normalize_vendor


def process_receipt_file(
    *,
    db: Session,
    storage: FileStorage,
    llm: LLMClient,
    user_id: int,
    filename: str,
    data: bytes,
    mime_type: str,
    source: ReceiptSource = ReceiptSource.UPLOAD,
    inbound_email_id: int | None = None,
) -> Receipt:
    file_key = f"receipts/{uuid4().hex}{FILE_EXTENSIONS[mime_type]}"
    storage.save(file_key, data, mime_type)

    receipt = Receipt(
        user_id=user_id,
        source=source,
        inbound_email_id=inbound_email_id,
        original_filename=filename,
        content_type=mime_type,
        file_key=file_key,
        file_sha256=hashlib.sha256(data).hexdigest(),
    )
    try:
        extracted = extract_receipt(llm, data, mime_type)
    except LLMError as exc:
        receipt.status = ReceiptStatus.FAILED
        receipt.extraction_error = str(exc)
        receipt.flags.append(
            ReceiptFlag(
                kind=FlagKind.EXTRACTION,
                code="extraction_failed",
                message="The receipt couldn't be read automatically.",
            )
        )
    else:
        apply_extraction(receipt, extracted, today=date.today())

    db.add(receipt)
    db.flush()  # assigns receipt.id, so the checks below can exclude this receipt

    if receipt.status == ReceiptStatus.EXTRACTED:
        analyze_receipt(db, llm, receipt)
    else:
        # Exact re-uploads can be spotted even when extraction failed.
        receipt.flags.extend(find_duplicate_flags(db, receipt))

    db.commit()
    return receipt


def apply_extraction(receipt: Receipt, extracted: ExtractedReceipt, today: date) -> None:
    """Copy extracted fields onto the receipt and flag any validation issues."""
    extracted = redact_extraction(extracted)  # never store a full card number
    receipt.status = ReceiptStatus.EXTRACTED
    receipt.raw_extraction = extracted.model_dump(mode="json")
    receipt.vendor = extracted.vendor
    receipt.vendor_key = normalize_vendor(extracted.vendor)
    receipt.purchase_date = parse_date(extracted.purchase_date)
    receipt.currency = (extracted.currency or "").upper()[:3] or None
    receipt.subtotal = money(extracted.subtotal)
    receipt.tax = money(extracted.tax)
    receipt.tip = money(extracted.tip)
    receipt.total = money(extracted.total)
    receipt.payment_method = extracted.payment_method
    receipt.line_items = [
        LineItem(
            position=i,
            description=item.description,
            quantity=quantity(item.quantity),
            unit_price=money(item.unit_price),
            amount=money(item.amount),
        )
        for i, item in enumerate(extracted.line_items)
    ]
    receipt.flags.extend(
        ReceiptFlag(kind=FlagKind.VALIDATION, code=issue.code, message=issue.message)
        for issue in validate_receipt(extracted, today=today)
    )


def analyze_receipt(db: Session, llm: LLMClient, receipt: Receipt) -> None:
    """Categorize, then look for duplicates and unusual charges.

    Categorizing comes first because the anomaly checks compare against the category.
    """
    assign_category(db, llm, receipt)
    receipt.flags.extend(find_duplicate_flags(db, receipt))
    receipt.flags.extend(find_anomaly_flags(db, receipt))
