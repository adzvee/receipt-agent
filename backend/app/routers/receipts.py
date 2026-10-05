"""HTTP routes for uploading and viewing receipts."""

from fastapi import APIRouter, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import DbSession
from app.file_types import sniff_mime_type
from app.llm import LLMDep
from app.models import Receipt
from app.receipt_service import process_receipt_upload
from app.schemas import ReceiptOut
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

    return process_receipt_upload(
        db=db,
        storage=storage,
        llm=llm,
        filename=file.filename or "receipt",
        data=data,
        mime_type=mime_type,
    )


@router.get("", response_model=list[ReceiptOut])
def list_receipts(db: DbSession) -> list[Receipt]:
    return list(db.scalars(select(Receipt).order_by(Receipt.created_at.desc(), Receipt.id.desc())))


@router.get("/{receipt_id}", response_model=ReceiptOut)
def get_receipt(receipt_id: int, db: DbSession) -> Receipt:
    return _get_or_404(db, receipt_id)


@router.get("/{receipt_id}/file")
def get_receipt_file(receipt_id: int, db: DbSession, storage: StorageDep) -> Response:
    receipt = _get_or_404(db, receipt_id)
    return Response(content=storage.read(receipt.file_key), media_type=receipt.content_type)


def _get_or_404(db: Session, receipt_id: int) -> Receipt:
    receipt = db.get(Receipt, receipt_id)
    if receipt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Receipt not found.")
    return receipt
