from decimal import Decimal

from app.anomalies import check_against_history, check_tip, detect_anomalies
from app.models import Category, Receipt


def d(*values: str) -> list[Decimal]:
    return [Decimal(v) for v in values]


def test_total_far_above_typical_is_an_outlier():
    history = d("10", "12", "11", "9", "13")  # median 11

    assert check_against_history(Decimal("40"), history, Decimal("3"), 5) == Decimal("11")
    assert check_against_history(Decimal("30"), history, Decimal("3"), 5) is None


def test_no_outlier_without_enough_history():
    assert check_against_history(Decimal("500"), d("10", "12"), Decimal("3"), 5) is None


def test_median_is_not_skewed_by_one_big_purchase():
    # An average would be ~208 here and hide the new 300 charge; the median (12) doesn't.
    history = d("10", "12", "11", "13", "1000")

    assert check_against_history(Decimal("300"), history, Decimal("3"), 5) == Decimal("12")


def test_high_tip():
    assert check_tip(Decimal("10"), Decimal("20")) == Decimal("0.5")
    assert check_tip(Decimal("4"), Decimal("20")) is None  # 20% is normal
    assert check_tip(None, Decimal("20")) is None


def test_detect_anomalies_explains_each_flag():
    receipt = Receipt(
        vendor="Corner Cafe",
        total=Decimal("60.00"),
        subtotal=Decimal("40.00"),
        tip=Decimal("20.00"),
        category=Category.DINING,
    )

    anomalies = detect_anomalies(
        receipt,
        category_history=d("10", "12", "11", "9", "13"),
        vendor_history=d("8", "9", "10"),
    )

    assert [a.code for a in anomalies] == ["high_for_category", "high_for_vendor", "high_tip"]
    assert anomalies[0].message == "60.00 is more than 3x your typical dining purchase (11.00)."
    assert anomalies[2].message == "The tip (20.00) is 50% of the subtotal."


def test_normal_receipt_has_no_anomalies():
    receipt = Receipt(vendor="Corner Cafe", total=Decimal("11.00"), category=Category.DINING)

    assert detect_anomalies(receipt, d("10", "12", "11", "9", "13"), d("8", "9", "10")) == []
