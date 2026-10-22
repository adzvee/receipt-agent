"""Comparing an extraction with its label, field by field.

Each field is judged the way a person checking the result would: amounts must match to
the cent, but "FRESH MART #112" is the same vendor as "Fresh Mart", and "VISA ****4242"
is the same payment method as "Visa ending 4242". When nothing is printed (e.g. no tip),
the correct answer is null, so inventing a value counts as wrong.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from app.extraction import ExtractedLineItem, ExtractedReceipt, money, parse_date
from app.validation import validate_receipt
from app.vendors import vendors_match

MONEY_FIELDS = ["subtotal", "tax", "tip", "total"]
FIELDS = [
    "vendor",
    "purchase_date",
    "currency",
    *MONEY_FIELDS,
    "payment_method",
    "line_items",
    "flag_decision",  # whether the app's validation flags it exactly when it should
]

# Most specific first: "VISA DEBIT" is Visa, and "INTERAC DEBIT" is Interac.
CARD_BRANDS = {
    "amex": ["amex", "american express"],
    "mastercard": ["mastercard", "master card"],
    "visa": ["visa"],
    "discover": ["discover"],
    "interac": ["interac"],
    "debit": ["debit"],
    "cash": ["cash"],
}


@dataclass(frozen=True)
class FieldResult:
    field: str
    correct: bool
    expected: Any
    actual: Any


@dataclass(frozen=True)
class ItemCounts:
    expected: int
    extracted: int
    matched: int


# --- Field comparisons ---


def payment_key(text: str | None) -> tuple[str | None, str | None] | None:
    """("visa", "4242") for "VISA ****4242" or "Visa ending in 4242"; None if no payment."""
    if not text:
        return None
    lowered = text.lower()
    brand = next(
        (key for key, names in CARD_BRANDS.items() if any(n in lowered for n in names)), None
    )
    digits = re.findall(r"\d{4}", text)
    return brand, digits[-1] if digits else None


def _words(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def descriptions_match(expected: str, actual: str) -> bool:
    a, b = _words(expected), _words(actual)
    return a in b or b in a or SequenceMatcher(None, a, b).ratio() >= 0.6


def match_line_items(expected: list[dict], actual: list[ExtractedLineItem]) -> ItemCounts:
    """Pair items with the same amount and a similar description; each used at most once."""
    unused = list(actual)
    matched = 0
    for item in expected:
        for candidate in unused:
            same_amount = money(candidate.amount) == Decimal(item["amount"])
            if same_amount and descriptions_match(item["description"], candidate.description):
                unused.remove(candidate)
                matched += 1
                break
    return ItemCounts(expected=len(expected), extracted=len(actual), matched=matched)


def score_sample(
    label: dict, actual: ExtractedReceipt, today: date
) -> tuple[list[FieldResult], ItemCounts]:
    expected = label["expected"]
    results = []

    def add(field: str, correct: bool, want: Any, got: Any) -> None:
        results.append(FieldResult(field, correct, want, got))

    want, got = expected["vendor"], actual.vendor
    add("vendor", vendors_match(want, got) if want else got is None, want, got)

    want, got = expected["purchase_date"], actual.purchase_date
    same_date = parse_date(want) == parse_date(got) and (want is None) == (got is None)
    add("purchase_date", same_date, want, got)

    want, got = expected["currency"], actual.currency
    add("currency", (want or "").upper() == (got or "").upper(), want, got)

    for field in MONEY_FIELDS:
        want, got = expected[field], getattr(actual, field)
        add(field, (Decimal(want) if want else None) == money(got), want, got)

    want, got = expected["payment_method"], actual.payment_method
    add("payment_method", payment_key(want) == payment_key(got), want, got)

    items = match_line_items(expected["line_items"], actual.line_items)
    all_items = items.matched == items.expected == items.extracted
    summary = f"{items.matched}/{items.expected} matched, {items.extracted} returned"
    add("line_items", all_items, f"{items.expected} items", summary)

    issues = validate_receipt(actual, today)
    want_flag = "flagged" if label["expect_flagged"] else "not flagged"
    got_flag = ", ".join(i.code for i in issues) if issues else "not flagged"
    add("flag_decision", bool(issues) == label["expect_flagged"], want_flag, got_flag)

    return results, items


def perfect_extraction(label: dict) -> ExtractedReceipt:
    """What a flawless model would return for a label (used to test the labels themselves)."""
    expected = label["expected"]

    def number(value: str | None) -> float | None:
        return float(value) if value is not None else None

    return ExtractedReceipt(
        vendor=expected["vendor"],
        purchase_date=expected["purchase_date"],
        currency=expected["currency"],
        line_items=[
            ExtractedLineItem(
                description=item["description"],
                quantity=number(item["quantity"]),
                unit_price=number(item["unit_price"]),
                amount=float(item["amount"]),
            )
            for item in expected["line_items"]
        ],
        **{field: number(expected[field]) for field in MONEY_FIELDS},
        payment_method=expected["payment_method"],
    )
