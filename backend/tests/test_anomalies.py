from decimal import Decimal

from app.anomalies import check_tip, detect_anomalies, high_end, typical
from app.models import Category, Receipt


def d(*values: str) -> list[Decimal]:
    return [Decimal(v) for v in values]


def receipt(total: str, **fields) -> Receipt:
    return Receipt(vendor="Corner Cafe", total=Decimal(total), category=Category.DINING, **fields)


def codes(r: Receipt, category_history=(), vendor_history=()) -> list[str]:
    return [a.code for a in detect_anomalies(r, list(category_history), list(vendor_history))]


# Mostly coffees, plus a couple of restaurant meals: a realistic "dining" history.
DINING = d("4.50", "5.25", "9.00", "6.75", "8.40", "42.00", "5.50", "47.50", "7.20", "6.10")


def test_high_end_and_typical():
    assert high_end(DINING) == Decimal("42.55")
    assert typical(DINING) == Decimal("6.98")  # middle values 6.75 and 7.20


def test_normal_dinner_is_not_flagged_even_though_most_dining_is_coffee():
    # $45 is ~7x the median coffee, but well within the high end of dining.
    assert codes(receipt("45.00"), DINING) == []


def test_charge_far_above_the_category_high_end_is_flagged():
    anomalies = detect_anomalies(receipt("230.00"), DINING, [])

    assert [a.code for a in anomalies] == ["high_for_category"]
    assert anomalies[0].message == (
        "230.00 is more than 2x the high end of your usual dining purchases (42.55)."
    )


def test_no_category_flag_without_enough_history():
    assert codes(receipt("500.00"), d("10", "12")) == []


def test_charge_far_above_vendor_median_is_flagged():
    anomalies = detect_anomalies(receipt("60.00"), [], d("18", "19", "20", "21", "22"))

    assert [a.code for a in anomalies] == ["high_for_vendor"]
    assert anomalies[0].message == (
        "60.00 is more than 2.5x what you usually spend at Corner Cafe (20.00)."
    )


def test_small_amounts_are_not_flagged_even_at_a_high_ratio():
    # A $12 café order is 3x a $4 coffee, but only $8 more: not worth reviewing.
    assert codes(receipt("12.00"), [], d("4", "4", "4.50", "4", "4.50")) == []
    # $28 is over 2x the category's high end ($5), but only $23 more.
    assert codes(receipt("28.00"), d("4", "5", "4", "5", "4", "5", "4", "5", "4", "5")) == []


def test_vendor_median_is_not_skewed_by_one_big_purchase():
    # An average would be ~208 here and hide the new 40 charge; the median (10) doesn't.
    assert codes(receipt("40.00"), [], d("9", "10", "10", "11", "1000")) == ["high_for_vendor"]


def test_no_vendor_flag_without_enough_history():
    assert codes(receipt("60.00"), [], d("18", "20", "22")) == []


def test_high_tip():
    assert check_tip(Decimal("10"), Decimal("20")) == Decimal("0.5")
    assert check_tip(Decimal("4"), Decimal("20")) is None  # 20% is normal
    assert check_tip(None, Decimal("20")) is None
    anomalies = detect_anomalies(
        receipt("30.00", subtotal=Decimal("20.00"), tip=Decimal("10.00")), [], []
    )
    assert anomalies[0].message == "The tip (10.00) is 50% of the subtotal."
