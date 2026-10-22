"""Full card numbers are masked before anything is saved. All numbers are test numbers."""

import pytest

from app.extraction import ExtractedLineItem, ExtractedReceipt
from app.models import Receipt
from app.redaction import mask_card_numbers
from tests.factories import make_extracted_receipt
from tests.fakes import PNG_BYTES

VISA_TEST_NUMBER = "4111111111111111"  # a standard test number; passes the Luhn check


@pytest.mark.parametrize(
    "text",
    [
        "VISA 4111111111111111",
        "Visa 4111 1111 1111 1111",
        "card 4111-1111-1111-1111 approved",
        "Amex 378282246310005",  # 15 digits
    ],
)
def test_full_card_numbers_are_masked_to_the_last_four(text):
    masked = mask_card_numbers(text)

    assert "1111 1111" not in masked and "411111" not in masked and "3782822" not in masked
    assert "•••• " in masked


def test_masking_keeps_the_last_four_and_the_rest_of_the_text():
    assert mask_card_numbers("Paid with Visa 4111 1111 1111 1111.") == "Paid with Visa •••• 1111."


@pytest.mark.parametrize(
    "text",
    [
        "Visa ending 4242",
        "VISA ************4242",
        "Order #4111111111111112",  # 16 digits, but fails the Luhn check: not a card
        "Phone 555 010 2231",  # too short
        "Total 1234.56",
    ],
)
def test_other_numbers_are_left_alone(text):
    assert mask_card_numbers(text) == text


def test_upload_stores_only_masked_card_numbers(client, fake_llm, db_session):
    fee = ExtractedLineItem(description=f"Card {VISA_TEST_NUMBER} fee", amount=7.75)
    fake_llm.responses[ExtractedReceipt] = make_extracted_receipt(
        payment_method=f"VISA {VISA_TEST_NUMBER}", line_items=[fee]
    )

    response = client.post("/receipts", files={"file": ("r.png", PNG_BYTES)})

    body = response.json()
    assert body["payment_method"] == "VISA •••• 1111"
    assert body["line_items"][0]["description"] == "Card •••• 1111 fee"
    saved = db_session.get(Receipt, body["id"])
    assert VISA_TEST_NUMBER not in str(saved.raw_extraction)  # nor in the raw model answer
