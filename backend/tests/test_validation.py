from datetime import date

from app.extraction import ExtractedLineItem
from app.validation import validate_receipt
from tests.factories import make_extracted_receipt

TODAY = date(2026, 10, 4)


def codes(receipt) -> list[str]:
    return [issue.code for issue in validate_receipt(receipt, today=TODAY)]


def test_consistent_receipt_has_no_issues():
    assert codes(make_extracted_receipt()) == []


def test_line_items_not_matching_subtotal_is_flagged():
    receipt = make_extracted_receipt(subtotal=9.00, total=9.62)

    assert codes(receipt) == ["line_items_mismatch"]


def test_total_not_matching_subtotal_plus_tax_is_flagged():
    receipt = make_extracted_receipt(total=10.00)

    assert codes(receipt) == ["total_mismatch"]


def test_tip_is_included_in_total():
    receipt = make_extracted_receipt(tip=1.50, total=9.87)

    assert codes(receipt) == []


def test_tax_already_included_in_prices_is_accepted():
    # e.g. a European receipt: prices include VAT, and VAT is shown for information only.
    receipt = make_extracted_receipt(tax=1.29, total=7.75)

    assert codes(receipt) == []


def test_small_rounding_difference_is_tolerated():
    receipt = make_extracted_receipt(total=8.38)

    assert codes(receipt) == []


def test_without_subtotal_line_items_are_compared_to_total():
    assert codes(make_extracted_receipt(subtotal=None)) == []
    assert codes(make_extracted_receipt(subtotal=None, total=20.00)) == ["total_mismatch"]


def test_discount_line_reduces_the_sum():
    receipt = make_extracted_receipt(
        line_items=[
            ExtractedLineItem(description="Latte", amount=4.50),
            ExtractedLineItem(description="Croissant", amount=3.25),
            ExtractedLineItem(description="Loyalty discount", amount=-1.00),
        ],
        subtotal=6.75,
        tax=0.54,
        total=7.29,
    )

    assert codes(receipt) == []


def test_missing_fields_are_flagged():
    receipt = make_extracted_receipt(vendor=None, purchase_date=None, total=None)

    assert codes(receipt) == ["missing_vendor", "missing_date", "missing_total"]


def test_invalid_and_future_dates_are_flagged():
    assert codes(make_extracted_receipt(purchase_date="14/09/2026")) == ["invalid_date"]
    assert codes(make_extracted_receipt(purchase_date="2026-12-25")) == ["future_date"]
