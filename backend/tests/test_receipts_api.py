from app.config import get_settings
from app.extraction import EXTRACTION_PROMPT, ExtractedReceipt
from app.llm import LLMError
from tests.factories import make_extracted_receipt
from tests.fakes import PDF_BYTES, PNG_BYTES


def upload(client, data: bytes, filename: str = "receipt.png"):
    return client.post("/receipts", files={"file": (filename, data)})


def test_upload_extracts_and_saves_receipt(client, fake_llm, storage):
    response = upload(client, PNG_BYTES)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "extracted"
    assert body["vendor"] == "Corner Cafe"
    assert body["purchase_date"] == "2026-09-14"
    assert body["total"] == "8.37"
    assert body["payment_method"] == "Visa ending 4242"
    assert [item["description"] for item in body["line_items"]] == ["Latte", "Croissant"]
    assert body["needs_review"] is False
    assert body["flags"] == []

    # The LLM was sent the actual file with the extraction prompt.
    [call] = fake_llm.calls_for(ExtractedReceipt)
    assert call["prompt"] == EXTRACTION_PROMPT
    assert call["attachments"][0].data == PNG_BYTES
    assert call["attachments"][0].mime_type == "image/png"


def test_upload_response_matches_what_was_saved(client, db_session):
    created = upload(client, PNG_BYTES).json()
    db_session.expire_all()  # force the next read to come from the database, not memory

    fetched = client.get(f"/receipts/{created['id']}").json()

    assert fetched == created
    assert fetched["line_items"][0]["quantity"] == "1.000"
    assert fetched["subtotal"] == "7.75"


def test_uploaded_file_is_stored_and_downloadable(client):
    receipt_id = upload(client, PDF_BYTES, "receipt.pdf").json()["id"]

    response = client.get(f"/receipts/{receipt_id}/file")

    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response.headers["content-type"] == "application/pdf"


def test_receipt_failing_validation_is_flagged(client, fake_llm):
    fake_llm.responses[ExtractedReceipt] = make_extracted_receipt(total=50.00)

    body = upload(client, PNG_BYTES).json()

    assert body["needs_review"] is True
    assert [(flag["kind"], flag["code"]) for flag in body["flags"]] == [
        ("validation", "total_mismatch")
    ]


def test_llm_failure_keeps_file_and_marks_receipt_failed(client, fake_llm):
    fake_llm.responses[ExtractedReceipt] = LLMError("model unavailable")

    response = upload(client, PNG_BYTES)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert body["extraction_error"] == "model unavailable"
    assert body["needs_review"] is True
    assert [flag["code"] for flag in body["flags"]] == ["extraction_failed"]
    assert body["category"] is None
    assert client.get(f"/receipts/{body['id']}/file").content == PNG_BYTES


def test_unsupported_file_type_is_rejected(client, fake_llm):
    response = upload(client, b"GIF89a" + b"\x00" * 10, "receipt.png")

    assert response.status_code == 415
    assert fake_llm.calls == []


def test_empty_file_is_rejected(client):
    assert upload(client, b"").status_code == 400


def test_too_large_file_is_rejected(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 32)

    assert upload(client, PNG_BYTES).status_code == 413


def test_list_and_get_receipts(client):
    first_id = upload(client, PNG_BYTES).json()["id"]
    second_id = upload(client, PDF_BYTES, "receipt.pdf").json()["id"]

    listed = client.get("/receipts").json()
    assert [r["id"] for r in listed][:2] == [second_id, first_id]

    assert client.get(f"/receipts/{first_id}").json()["id"] == first_id


def test_missing_receipt_returns_404(client):
    assert client.get("/receipts/999999").status_code == 404
    assert client.get("/receipts/999999/file").status_code == 404
