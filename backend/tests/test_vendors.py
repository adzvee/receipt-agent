import pytest

from app.vendors import normalize_vendor, vendors_match


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("STARBUCKS #1234", "starbucks"),
        ("The Corner Café, Inc.", "corner café"),
        ("Trader Joe's 552", "trader joe s"),
        ("  ", None),
        (None, None),
    ],
)
def test_normalize_vendor(name, expected):
    assert normalize_vendor(name) == expected


def test_same_business_written_differently_matches():
    assert vendors_match("STARBUCKS #1234", "Starbucks")
    assert vendors_match("Corner Cafe", "The Corner Cafe Inc")
    assert vendors_match("Whole Foods Market", "Whole Foods Mkt")  # close spelling


def test_different_businesses_do_not_match():
    assert not vendors_match("Corner Cafe", "Corner Bakery")
    assert not vendors_match("Target", "Walmart")
    assert not vendors_match(None, "Target")
