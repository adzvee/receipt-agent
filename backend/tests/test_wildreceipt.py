"""The WildReceipt evaluation: label parsing, scoring, and resuming. No dataset needed:
these tests use small made-up label lines in WildReceipt's format."""

import json
from datetime import date
from decimal import Decimal

import pytest

from app.extraction import ExtractedReceipt
from app.llm import LLMError, TokenUsage
from evaluation.wildreceipt import (
    LabeledReceipt,
    amount_candidates,
    date_candidates,
    date_order,
    evaluate,
    parse_amount,
    parse_label_line,
    sample,
    score_receipt,
)

TODAY = date(2026, 10, 26)


def box(text: str, label: int, top: float, left: float = 10.0) -> dict:
    """A WildReceipt annotation: 8 corner coordinates, the text, and its class id."""
    right, bottom = left + 100, top + 18
    return {
        "box": [left, bottom, right, bottom, right, top, left, top],
        "text": text,
        "label": label,
    }


def label_line(file_name: str, *annotations: dict) -> str:
    return json.dumps(
        {"file_name": file_name, "height": 400, "width": 300, "annotations": list(annotations)}
    )


def receipt(all_text: tuple[str, ...] = (), **boxes: list[str]) -> LabeledReceipt:
    return LabeledReceipt(id="r1", image=None, boxes=boxes, all_text=all_text)  # type: ignore[arg-type]


def answer(**fields) -> ExtractedReceipt:
    values = {
        "vendor": None,
        "purchase_date": None,
        "currency": None,
        "line_items": [],
        "subtotal": None,
        "tax": None,
        "tip": None,
        "total": None,
        "payment_method": None,
    }
    return ExtractedReceipt(**{**values, **fields})


def outcome(labeled: LabeledReceipt, extracted: ExtractedReceipt, field: str):
    outcomes, _ = score_receipt(labeled, extracted)
    return next(o for o in outcomes if o.field == field)


# --- Reading labels ---


def test_boxes_are_joined_per_field_in_reading_order(tmp_path):
    line = label_line(
        "image_files/Image_1/0/abc123.jpeg",
        box("KOREANRESTAURANT", 1, top=20),  # second line of the store name
        box("CHOEUN", 1, top=1),
        box("$13.99", 15, top=150),  # a product price: not scored
        box("TOTAL", 24, top=200),  # a key, not a value
        box("$38.77", 23, top=200, left=200),
    )

    parsed = parse_label_line(line, tmp_path)

    assert parsed.id == "abc123"
    assert parsed.image == tmp_path / "image_files/Image_1/0/abc123.jpeg"
    assert parsed.boxes == {"store_name": ["CHOEUN", "KOREANRESTAURANT"], "total": ["$38.77"]}
    assert "$13.99" in parsed.all_text  # every box is kept for currency clues


def test_sample_order_is_fixed_and_smaller_runs_are_a_prefix():
    receipts = [
        LabeledReceipt(id=f"id{n}", image=None, boxes={})  # type: ignore[arg-type]
        for n in range(50)
    ]

    first_ten = [r.id for r in sample(receipts, 10)]

    assert first_ten == [r.id for r in sample(list(reversed(receipts)), 10)]
    assert first_ten == [r.id for r in sample(receipts, None)][:10]
    assert first_ten != [f"id{n}" for n in range(10)]  # shuffled, not file order


# --- Normalizing dates and amounts ---


@pytest.mark.parametrize(
    ("text", "dates"),
    [
        ("12/30/2016FRI", {date(2016, 12, 30)}),
        ("2014-07-22", {date(2014, 7, 22)}),
        ("28-Jun-2015", {date(2015, 6, 28)}),
        ("Aug15.2017", {date(2017, 8, 15)}),
        ("JAN09'03", {date(2003, 1, 9)}),
        ("14/02/18", {date(2018, 2, 14)}),  # only day-first is a real date
        ("05/02/18", {date(2018, 5, 2), date(2018, 2, 5)}),  # either way round
        ("08.06.95", {date(1995, 6, 8), date(1995, 8, 6)}),
        ("0ct25'14", {date(2014, 10, 25)}),  # OCR read the O as a zero
        ("27Dec´16", {date(2016, 12, 27)}),
        ("Jun15", set()),  # no year: can't be scored
        ("20:37", set()),
    ],
)
def test_date_labels_become_every_date_they_could_mean(text, dates):
    assert date_candidates(text) == dates


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("$65.36", "65.36"),
        ("£596.99", "596.99"),
        ("Eur154,40", "154.40"),
        ("0,47", "0.47"),
        (".26", "0.26"),
        ("1,360.00", "1360.00"),
        ("1.360,00", "1360.00"),
        ("19.729", "19.73"),
        ("TOTAL", None),
    ],
)
def test_amount_labels_are_normalized(text, amount):
    assert parse_amount(text) == (Decimal(amount) if amount else None)


def test_an_ambiguous_date_can_be_read_in_one_order():
    assert date_candidates("05/02/18", "month_first") == {date(2018, 5, 2)}
    assert date_candidates("05/02/18", "day_first") == {date(2018, 2, 5)}


def test_repeated_amount_boxes_collapse_and_tax_lines_may_be_summed():
    assert amount_candidates("total", ["$85.00", "$85.00"]) == {Decimal("85.00")}
    assert amount_candidates("tax", ["1.20", "0.30"]) == {
        Decimal("1.20"),
        Decimal("0.30"),
        Decimal("1.50"),
    }


# --- Scoring and error types ---


def test_store_names_ignore_case_spaces_and_punctuation():
    labeled = receipt(store_name=["CHOEUN", "KOREANRESTAURANT"])

    result = outcome(labeled, answer(vendor="Choeun Korean Restaurant"), "store_name")

    assert result.correct and result.note is None


def test_close_store_names_count_but_are_reported_as_close():
    labeled = receipt(store_name=["KELLYO‘s", "KellyO'Bryan's"])  # logo + printed name

    result = outcome(labeled, answer(vendor="Kelly O'Bryan's"), "store_name")

    assert result.correct and result.note == "close match"


def test_a_different_store_name_is_wrong():
    result = outcome(receipt(store_name=["SushiYasuda"]), answer(vendor="Walmart"), "store_name")

    assert not result.correct and result.error == "different name"


@pytest.mark.parametrize(
    ("label", "got", "correct", "error"),
    [
        ("12/30/2016", "2016-12-30", True, None),
        ("14/02/18", "2018-14-02", False, "not a valid date"),
        ("14/02/18", "2016-02-14", False, "wrong year"),
        ("12/30/2016", "2016-03-12", False, "different date"),
        ("12/30/2016", None, False, "missing"),
    ],
)
def test_dates(label, got, correct, error):
    result = outcome(receipt(date=[label]), answer(purchase_date=got), "date")

    assert (result.correct, result.error) == (correct, error)


# --- Ambiguous dates: the receipt's country decides ---


@pytest.mark.parametrize(
    ("clues", "order", "why"),
    [
        ({"address": ["SNELLVILLE,GA30078"]}, "month_first", "US state + ZIP"),
        ({"address": ["Coeurd'Alene,Idaho83814"]}, "month_first", "US state + ZIP"),
        ({"phone": ["(714)879-3574"]}, "month_first", "North American phone number"),
        ({"address": ["STRATHMOREVIC3041"]}, "day_first", "Australian state"),
        ({"address": ["MorrisonsplcBD37DL"]}, "day_first", "UK postcode"),
        ({"address": ["singapore079027"]}, "day_first", "country or city name"),
        ({"phone": ["+6566046861"]}, "day_first", "international phone code"),
        ({"all_text": ("£5.99",)}, "day_first", "currency or VAT"),
        ({"all_text": ("Eur154,40",)}, "day_first", "currency or VAT"),
        ({"all_text": ("Incl.VAT(20%):",)}, "day_first", "currency or VAT"),
        ({"address": ["VANCOUVER,BCV6M1L1"]}, None, "could be Canadian"),
        ({"phone": ["(416)555-0199"]}, None, "could be Canadian"),  # a Toronto area code
        ({"address": ["NEWYORK,NY10019"], "all_text": ("£5.99",)}, None, "clues disagree"),
        ({"address": ["KARLJOHANSGATE18c"]}, None, "no country clue"),
    ],
)
def test_country_clues_decide_the_date_order(clues, order, why):
    labeled = receipt(**clues)

    assert date_order(labeled) == (order, why)


@pytest.mark.parametrize(
    "clues",
    [
        {"all_text": ("AVOCADOMOUSSE",)},  # "CAD" inside a word isn't Canadian dollars
        {"all_text": ("Bone-inRibeye",)},  # nor is "INR" Indian rupees
        {"address": ["Audubon,NJ08106"]},  # "AUD": still just New Jersey
        {"address": ["Indianapolis,IN46204"]},  # "INDIA" inside INDIANA(POLIS)
    ],
)
def test_lookalike_words_are_not_country_clues(clues):
    order, _ = date_order(receipt(**clues))

    assert order in (None, "month_first")  # never day-first or "could be Canadian"


def test_ambiguous_date_is_scored_in_the_receipts_countrys_order():
    us = receipt(date=["05/02/18"], address=["Seattle,WA98122"])
    uk = receipt(date=["05/02/18"], all_text=("£12.00",))

    assert outcome(us, answer(purchase_date="2018-05-02"), "date").correct
    assert not outcome(us, answer(purchase_date="2018-02-05"), "date").correct
    assert outcome(uk, answer(purchase_date="2018-02-05"), "date").correct
    wrong = outcome(uk, answer(purchase_date="2018-05-02"), "date")
    assert wrong.error == "day and month swapped"
    assert wrong.note == "ambiguous, read day-first (currency or VAT)"


def test_ambiguous_date_without_a_clear_country_is_left_out():
    outcomes, skipped = score_receipt(
        receipt(date=["05/02/18"]), answer(purchase_date="2018-05-02")
    )

    assert outcomes == []
    assert skipped == ["date: ambiguous, no country clue"]


def test_day_and_month_swapped_is_named():
    result = outcome(receipt(date=["2014-07-08"]), answer(purchase_date="2014-08-07"), "date")

    assert result.error == "day and month swapped"


@pytest.mark.parametrize(
    ("got", "error"),
    [
        (38.77, None),
        (35.50, "gave the subtotal instead"),
        (3877.0, "decimal point misplaced"),
        (38.71, "one digit misread"),
        (12.00, "different amount"),
        (None, "missing"),
    ],
)
def test_amount_errors_are_classified(got, error):
    labeled = receipt(total=["$38.77"], subtotal=["35.50"])

    result = outcome(labeled, answer(total=got, subtotal=35.50), "total")

    assert result.correct == (error is None)
    assert result.error == error


def test_fields_without_a_label_are_not_scored():
    outcomes, skipped = score_receipt(receipt(total=["9.35"]), answer(total=9.35, tax=1.0))

    assert [o.field for o in outcomes] == ["total"]
    assert skipped == []


def test_unreadable_labels_are_reported_not_scored():
    outcomes, skipped = score_receipt(receipt(date=["Jun15"]), answer(purchase_date=None))

    assert outcomes == []
    assert skipped == ["date: label has no full date"]


# --- Running, resuming, and the report ---


class ScriptedLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def generate_structured(self, *, prompt, response_model, attachments=None):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def make_receipts(tmp_path, count: int) -> list[LabeledReceipt]:
    receipts = []
    for n in range(count):
        image = tmp_path / f"r{n}.jpeg"
        image.write_bytes(b"\xff\xd8\xff\xe0 fake jpeg")
        receipts.append(
            LabeledReceipt(f"r{n}", image, {"store_name": ["CORNERCAFE"], "total": ["$8.37"]})
        )
    return receipts


def run(llm, receipts, tmp_path):
    return evaluate(
        llm=llm,
        model="fake",
        receipts=receipts,
        raw_dir=tmp_path / "raw",
        today=TODAY,
        log=lambda _: None,
    )


def test_report_has_accuracy_errors_and_examples(tmp_path):
    receipts = make_receipts(tmp_path, 2)
    llm = ScriptedLLM(
        [answer(vendor="Corner Cafe", total=8.37), answer(vendor="Corner Cafe", total=8.31)]
    )

    report = run(llm, receipts, tmp_path)
    markdown = report.to_markdown()

    assert "| total | 50% | 1/2 | 2 |" in markdown
    assert "| store name | 100% | 2/2 | 2 |" in markdown
    assert "| total | one digit misread | 1 |" in markdown
    assert "label `$8.37`, model `8.31`" in markdown


def test_report_counts_ambiguous_dates_scored_and_left_out(tmp_path):
    receipts = make_receipts(tmp_path, 2)
    receipts[0].boxes.update(date=["05/02/18"], address=["Seattle,WA98122"])
    receipts[1].boxes.update(date=["05/02/18"])  # no country clue
    llm = ScriptedLLM([answer(purchase_date="2018-05-02")] * 2)

    markdown = run(llm, receipts, tmp_path).to_markdown()

    assert "| date | 100% | 1/1 | 1 |" in markdown
    assert "1 scored using the country" in markdown and "(1 month-first, 0 day-first)" in markdown
    assert "**1 left out**" in markdown
    assert "- date: ambiguous, no country clue: 1" in markdown


def test_a_run_stopped_by_the_quota_resumes_where_it_left_off(tmp_path):
    receipts = make_receipts(tmp_path, 4)
    quota = LLMError("Gemini request failed: 429 RESOURCE_EXHAUSTED. {...}")
    first = ScriptedLLM([answer(total=8.37), quota, quota])

    report = run(first, receipts, tmp_path)

    assert first.calls == 3  # stopped after two failures in a row
    assert report.scored_receipts == 1
    assert "1 of 4 so far" in report.to_markdown()

    second = ScriptedLLM([answer(total=8.37)] * 3)
    report = run(second, receipts, tmp_path)

    assert second.calls == 3  # only the ones that were missing
    assert report.scored_receipts == 4 and not report.errors


class MeteredLLM(ScriptedLLM):
    """Reports 1,000 input and 100 output tokens per call, like Gemini's usage data."""

    last_usage = TokenUsage(input_tokens=1000, output_tokens=100, thinking_tokens=40)


def test_token_usage_is_saved_and_totaled_across_resumed_runs(tmp_path):
    receipts = make_receipts(tmp_path, 3)
    quota = LLMError("503 UNAVAILABLE")
    run(MeteredLLM([answer(total=8.37), quota, quota]), receipts, tmp_path)

    report = run(MeteredLLM([answer(total=8.37)] * 2), receipts, tmp_path)

    assert report.receipts_with_usage == 3  # 1 saved earlier + 2 now
    assert report.usage == TokenUsage(3000, 300, 120)
    assert "3,000 input, 300 output (of which 120 thinking), 3,300 total" in report.to_markdown()
