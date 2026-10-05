"""HTTP routes for uploading and viewing receipts."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import DbSession
from app.file_types import sniff_mime_type
from app.llm import LLMDep
from app.models import Category, CategorySource, Receipt, ReceiptFlag
from app.receipt_service import process_receipt_file
from app.schemas import ReceiptOut, ReceiptUpdate
from app.storage import StorageDep

router = APIRouter(prefix="/receipts", tags=["receipts"])


# Routes are plain `def` (not `async def`) because the LLM and database calls block;
# FastAPI runs sync routes in a thread pool so they don't stall other requests.


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ReceiptOut)
def upload_receipt(file: UploadFile, db: DbSession, storage: StorageDep, llm: LLMDep) -> Receipt:
    max_bytes = get_settings().max_upload_bytes
    data = file.file.read(max_bytes + 1)

    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"File is larger than {max_bytes // (1024 * 1024)} MB.",
        )
    mime_type = sniff_mime_type(data)
    if mime_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Unsupported file type. Upload a JPEG, PNG, or WebP image, or a PDF.",
        )

    return process_receipt_file(
        db=db,
        storage=storage,
        llm=llm,
        filename=file.filename or "receipt",
        data=data,
        mime_type=mime_type,
    )


@router.get("", response_model=list[ReceiptOut])
def list_receipts(db: DbSession, needs_review: bool | None = None) -> list[Receipt]:
    """List receipts, most recent purchase first. `?needs_review=true` for flagged ones only.

    Receipts without a date (e.g. unreadable ones) come first, since they need attention.
    """
    query = select(Receipt).order_by(
        Receipt.purchase_date.desc().nulls_first(), Receipt.created_at.desc(), Receipt.id.desc()
    )
    if needs_review is not None:
        has_open_flag = Receipt.flags.any(ReceiptFlag.dismissed_at.is_(None))
        query = query.where(has_open_flag if needs_review else ~has_open_flag)
    return list(db.scalars(query))


@router.get("/categories", response_model=list[Category])
def list_categories() -> list[Category]:
    return list(Category)


@router.get("/{receipt_id}", response_model=ReceiptOut)
def get_receipt(receipt_id: int, db: DbSession) -> Receipt:
    return _get_or_404(db, receipt_id)


@router.patch("/{receipt_id}", response_model=ReceiptOut)
def update_receipt(receipt_id: int, update: ReceiptUpdate, db: DbSession) -> Receipt:
    """Correct a receipt's category. Future receipts from the same vendor will reuse it."""
    receipt = _get_or_404(db, receipt_id)
    receipt.category = update.category
    receipt.category_source = CategorySource.USER
    receipt.category_reason = "Set by you."
    db.commit()
    return receipt


@router.post("/{receipt_id}/flags/{flag_id}/dismiss", response_model=ReceiptOut)
def dismiss_flag(receipt_id: int, flag_id: int, db: DbSession) -> Receipt:
    """Mark a flag as reviewed (e.g. "not actually a duplicate")."""
    receipt = _get_or_404(db, receipt_id)
    flag = next((f for f in receipt.flags if f.id == flag_id), None)
    if flag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Flag not found on this receipt.")
    if flag.dismissed_at is None:
        flag.dismissed_at = datetime.now(UTC)
        db.commit()
    return receipt


@router.get("/{receipt_id}/file")
def get_receipt_file(receipt_id: int, db: DbSession, storage: StorageDep) -> Response:
    receipt = _get_or_404(db, receipt_id)
    return Response(
        content=storage.read(receipt.file_key),
        media_type=receipt.content_type,
        # Stop browsers from guessing a different type (e.g. treating text as HTML).
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _get_or_404(db: Session, receipt_id: int) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found.")
    return receipt
