"""The upload pipeline: store the file, extract with the LLM, validate, save to the database."""

import hashlib
from dataclasses import asdict
from datetime import date
from uuid import uuid4

from sqlalchemy.orm import Session

from app.extraction import ExtractedReceipt, extract_receipt, money, parse_date, quantity
from app.file_types import SUPPORTED_EXTENSIONS
from app.llm import LLMClient, LLMError
from app.models import LineItem, Receipt, ReceiptStatus
from app.storage import FileStorage
from app.validation import validate_receipt


def process_receipt_upload(
    *,
    db: Session,
    storage: FileStorage,
    llm: LLMClient,
    filename: str,
    data: bytes,
    mime_type: str,
) -> Receipt:
    file_key = f"receipts/{uuid4().hex}{SUPPORTED_EXTENSIONS[mime_type]}"
    storage.save(file_key, data, mime_type)

    receipt = Receipt(
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
        receipt.needs_review = True
    else:
        apply_extraction(receipt, extracted, today=date.today())

    db.add(receipt)
    db.commit()
    return receipt


def apply_extraction(receipt: Receipt, extracted: ExtractedReceipt, today: date) -> None:
    """Copy extracted fields onto the receipt and record any validation issues."""
    issues = validate_receipt(extracted, today=today)

    receipt.status = ReceiptStatus.EXTRACTED
    receipt.raw_extraction = extracted.model_dump(mode="json")
    receipt.vendor = extracted.vendor
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
    receipt.validation_issues = [asdict(issue) for issue in issues]
    receipt.needs_review = bool(issues)
