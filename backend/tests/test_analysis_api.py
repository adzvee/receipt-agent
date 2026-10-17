"""Categorization, duplicate detection, and anomaly flags, tested through the API."""

from app.categorization import CategoryDecision
from app.extraction import ExtractedReceipt
from app.llm import LLMError
from app.models import Category, CategorySource
from tests.factories import add_receipt, make_category_decision, make_extracted_receipt
from tests.fakes import PNG_BYTES, unique_png


def upload(client, data: bytes = PNG_BYTES) -> dict:
    response = client.post("/receipts", files={"file": ("receipt.png", data)})
    assert response.status_code == 201
    return response.json()


def flag_codes(receipt: dict) -> list[str]:
    return [flag["code"] for flag in receipt["flags"]]


# --- Categorization ---


def test_new_vendor_is_categorized_by_llm(client, fake_llm):
    fake_llm.responses[CategoryDecision] = make_category_decision(Category.DINING)

    body = upload(client)

    assert body["category"] == "dining"
    assert body["category_source"] == "llm"
    assert body["category_reason"] == "It's a café."
    [call] = fake_llm.calls_for(CategoryDecision)
    assert "Vendor: Corner Cafe" in call["prompt"]
    assert "Latte" in call["prompt"]
    assert call["attachments"] == []  # categorizes from extracted text, not the image


def test_known_vendor_reuses_category_without_llm(client, fake_llm, db_session):
    earlier = add_receipt(db_session, vendor="CORNER CAFE #12", category=Category.GROCERIES)

    body = upload(client)

    assert body["category"] == "groceries"
    assert body["category_source"] == "vendor_history"
    assert body["category_reason"] == f"Same vendor as receipt #{earlier.id}."
    assert fake_llm.calls_for(CategoryDecision) == []


def test_user_correction_wins_over_newer_llm_category(client, db_session):
    add_receipt(db_session, category=Category.OFFICE, category_source=CategorySource.USER)
    add_receipt(db_session, category=Category.DINING, category_source=CategorySource.LLM)

    assert upload(client)["category"] == "office"


def test_categorization_failure_leaves_receipt_uncategorized(client, fake_llm):
    fake_llm.responses[CategoryDecision] = LLMError("model unavailable")

    body = upload(client)

    assert body["status"] == "extracted"
    assert body["category"] is None


def test_user_can_change_category(client):
    receipt_id = upload(client)["id"]

    response = client.patch(f"/receipts/{receipt_id}", json={"category": "education"})

    assert response.status_code == 200
    assert response.json()["category"] == "education"
    assert response.json()["category_source"] == "user"


def test_invalid_category_is_rejected(client):
    receipt_id = upload(client)["id"]

    response = client.patch(f"/receipts/{receipt_id}", json={"category": "snacks"})

    assert response.status_code == 422


def test_list_categories(client):
    response = client.get("/receipts/categories")

    assert response.status_code == 200
    assert "groceries" in response.json()
    assert "other" in response.json()


# --- Duplicates ---


def test_same_file_uploaded_twice_is_flagged(client):
    first = upload(client)

    second = upload(client)

    assert flag_codes(first) == []
    assert flag_codes(second) == ["duplicate_file"]
    assert second["flags"][0]["related_receipt_id"] == first["id"]


def test_same_file_is_flagged_even_when_extraction_fails(client, fake_llm):
    first = upload(client)
    fake_llm.responses[ExtractedReceipt] = LLMError("model unavailable")

    second = upload(client)

    assert flag_codes(second) == ["extraction_failed", "duplicate_file"]
    assert second["flags"][1]["related_receipt_id"] == first["id"]


def test_same_purchase_in_a_different_file_is_flagged(client, fake_llm):
    first = upload(client, unique_png(1))
    # e.g. a phone photo of the same receipt, where the vendor is printed slightly differently
    fake_llm.responses[ExtractedReceipt] = make_extracted_receipt(vendor="THE CORNER CAFE")

    second = upload(client, unique_png(2))

    assert flag_codes(second) == ["likely_duplicate"]
    assert second["flags"][0]["related_receipt_id"] == first["id"]


def test_same_vendor_different_day_is_not_a_duplicate(client, fake_llm):
    upload(client, unique_png(1))
    fake_llm.responses[ExtractedReceipt] = make_extracted_receipt(purchase_date="2026-09-15")

    assert flag_codes(upload(client, unique_png(2))) == []


# --- Anomalies ---


def test_unusually_large_charge_is_flagged(client, fake_llm, db_session):
    for total in ["9.00", "11.00", "10.00", "12.00", "8.00"] * 2:
        add_receipt(db_session, vendor="Some Other Cafe", total=total)
    fake_llm.responses[ExtractedReceipt] = make_extracted_receipt(
        line_items=[], subtotal=None, tax=None, total=95.00
    )

    body = upload(client)

    assert flag_codes(body) == ["high_for_category"]
    assert body["flags"][0]["kind"] == "anomaly"
    assert "the high end of your usual dining purchases (12.00)" in body["flags"][0]["message"]


def test_history_in_another_currency_is_ignored(client, fake_llm, db_session):
    for total in ["9.00", "11.00", "10.00", "12.00", "8.00"] * 2:
        add_receipt(db_session, vendor="Some Other Cafe", total=total, currency="EUR")
    fake_llm.responses[ExtractedReceipt] = make_extracted_receipt(
        line_items=[], subtotal=None, tax=None, total=95.00
    )

    assert flag_codes(upload(client)) == []


# --- Reviewing flags ---


def test_dismissing_the_last_flag_clears_needs_review(client):
    upload(client)
    duplicate = upload(client)
    flag_id = duplicate["flags"][0]["id"]

    response = client.post(f"/receipts/{duplicate['id']}/flags/{flag_id}/dismiss")

    assert response.status_code == 200
    body = response.json()
    assert body["needs_review"] is False
    assert body["flags"][0]["dismissed_at"] is not None


def test_dismissing_unknown_flag_returns_404(client):
    receipt_id = upload(client)["id"]

    assert client.post(f"/receipts/{receipt_id}/flags/999999/dismiss").status_code == 404


def test_filter_receipts_needing_review(client):
    clean = upload(client)
    flagged = upload(client)  # same file again -> duplicate flag

    flagged_ids = [r["id"] for r in client.get("/receipts?needs_review=true").json()]
    clean_ids = [r["id"] for r in client.get("/receipts?needs_review=false").json()]

    assert flagged["id"] in flagged_ids and clean["id"] not in flagged_ids
    assert clean["id"] in clean_ids and flagged["id"] not in clean_ids
