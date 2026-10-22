"""The evaluation's labels and scoring. No real LLM calls: the model is faked."""

import json
from datetime import date

import pytest

from app.extraction import ExtractedLineItem, ExtractedReceipt
from app.file_types import sniff_mime_type
from app.llm import LLMError
from evaluation.run import evaluate, load_labels
from evaluation.samples import LABELS_FILE, SAMPLES_DIR, write_samples
from evaluation.scoring import FIELDS, payment_key, perfect_extraction, score_sample

TODAY = date(2026, 10, 22)
LABELS = load_labels()


def by_id(sample_id: str) -> dict:
    return next(label for label in LABELS if label["id"] == sample_id)


def wrong_fields(label: dict, extraction: ExtractedReceipt) -> set[str]:
    results, _ = score_sample(label, extraction, TODAY)
    return {r.field for r in results if not r.correct}


# --- The labels themselves ---


def test_labels_match_the_code_that_generates_them(tmp_path):
    assert write_samples(tmp_path) == json.loads(LABELS_FILE.read_text())


@pytest.mark.parametrize("label", LABELS, ids=lambda label: label["id"])
def test_each_sample_file_exists_with_the_labeled_type(label):
    data = (SAMPLES_DIR / label["file"]).read_bytes()
    assert sniff_mime_type(data) == label["mime_type"]


@pytest.mark.parametrize("label", LABELS, ids=lambda label: label["id"])
def test_a_perfect_extraction_scores_every_field_correct(label):
    # This also checks the labels' arithmetic: unflagged samples must pass the app's
    # validation, and the deliberately broken ones must fail it.
    assert wrong_fields(label, perfect_extraction(label)) == set()


def test_the_set_includes_receipts_that_should_be_flagged():
    assert {label["id"] for label in LABELS if label["expect_flagged"]} == {
        "misprinted_total",
        "no_date",
    }


# --- Scoring rules ---


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Visa ending 4242", "VISA ************4242"),
        ("Visa ending 5108", "Visa Debit ending in 5108"),
        ("Amex ending 1007", "American Express ****1007"),
        ("Interac ending 3350", "INTERAC DEBIT ****3350"),
        ("Visa ending 0044", "Apple Pay (Visa ending 0044)"),
        ("Cash", "CASH"),
    ],
)
def test_payment_methods_match_by_brand_and_last_four(a, b):
    assert payment_key(a) == payment_key(b)


def test_payment_with_different_digits_is_wrong():
    assert payment_key("Visa ending 4242") != payment_key("Visa ending 4243")


def test_vendor_name_variants_count_as_correct():
    label = by_id("grocery_clean")
    extraction = perfect_extraction(label).model_copy(update={"vendor": "FRESH MART #112"})

    assert wrong_fields(label, extraction) == set()


def test_inventing_a_value_that_is_not_printed_is_wrong():
    label = by_id("grocery_clean")  # no tip printed
    extraction = perfect_extraction(label).model_copy(update={"tip": 0.0})

    assert "tip" in wrong_fields(label, extraction)


def test_guessing_a_currency_that_is_not_printed_is_wrong():
    label = by_id("no_currency_symbol")
    extraction = perfect_extraction(label).model_copy(update={"currency": "USD"})

    assert wrong_fields(label, extraction) == {"currency"}


def test_fixing_a_misprinted_total_is_wrong_and_hides_the_problem():
    label = by_id("misprinted_total")
    extraction = perfect_extraction(label).model_copy(update={"total": 28.30})  # "corrected"

    assert wrong_fields(label, extraction) == {"total", "flag_decision"}


def test_a_missing_or_extra_line_item_is_wrong():
    label = by_id("cafe_us_date")
    perfect = perfect_extraction(label)
    extra = ExtractedLineItem(description="Gratuity", amount=1.00)

    missing_one = perfect.model_copy(update={"line_items": perfect.line_items[:1]})
    one_extra = perfect.model_copy(update={"line_items": [*perfect.line_items, extra]})

    assert "line_items" in wrong_fields(label, missing_one)
    assert "line_items" in wrong_fields(label, one_extra)


def test_swapped_day_and_month_is_wrong():
    label = by_id("cafe_us_date")
    extraction = perfect_extraction(label).model_copy(update={"purchase_date": "2026-10-04"})

    assert wrong_fields(label, extraction) == {"purchase_date"}


# --- The runner ---


class ScriptedLLM:
    """Returns a perfect extraction for each sample in turn, or raises a queued error."""

    def __init__(self, labels, errors=None):
        self.answers = [perfect_extraction(label) for label in labels]
        self.errors = errors or {}
        self.calls = 0

    def generate_structured(self, *, prompt, response_model, attachments=None):
        self.calls += 1
        if self.calls in self.errors:
            self.answers.pop(0)
            raise self.errors[self.calls]
        return self.answers.pop(0)


def run(llm, labels, tmp_path, **kwargs):
    return evaluate(
        llm=llm,
        model="fake",
        labels=labels,
        raw_dir=tmp_path,
        today=TODAY,
        log=lambda _: None,
        **kwargs,
    )


def test_report_shows_every_field_and_saves_raw_answers(tmp_path):
    labels = LABELS[:3]
    report = run(ScriptedLLM(labels), labels, tmp_path)

    markdown = report.to_markdown()
    for name in FIELDS:
        assert f"| {name} | 100% | 3/3 |" in markdown
    assert "Mistakes\n\nNone." in markdown
    assert sorted(p.stem for p in tmp_path.iterdir()) == sorted(label["id"] for label in labels)


def test_saved_answers_are_reused_without_calling_the_model(tmp_path):
    labels = LABELS[:2]
    run(ScriptedLLM(labels), labels, tmp_path)

    again = ScriptedLLM(labels)
    report = run(again, labels, tmp_path)

    assert again.calls == 0
    assert len(report.results) == 2


def test_failed_calls_are_reported_not_scored_and_retried_next_time(tmp_path):
    labels = LABELS[:3]
    report = run(ScriptedLLM(labels, errors={2: LLMError("429 quota")}), labels, tmp_path)

    assert list(report.errors) == [labels[1]["id"]]
    assert len(report.results) == 2
    assert "Not scored" in report.to_markdown()

    retry = ScriptedLLM([labels[1]])
    run(retry, labels, tmp_path)
    assert retry.calls == 1  # only the failed one


def test_waits_between_live_calls(tmp_path):
    labels = LABELS[:3]
    waits = []
    run(ScriptedLLM(labels), labels, tmp_path, delay_seconds=13, sleep=waits.append)

    assert waits == [13, 13]  # not before the first call


def test_stops_calling_the_model_after_repeated_failures(tmp_path):
    labels = LABELS[:5]
    quota = LLMError("Gemini request failed: 429 RESOURCE_EXHAUSTED. {'error': {...}}")
    llm = ScriptedLLM(labels, errors={1: quota, 2: quota})

    report = run(llm, labels, tmp_path)

    assert llm.calls == 2  # the other 3 weren't tried
    assert report.errors[labels[0]["id"]] == "Gemini request failed: 429 RESOURCE_EXHAUSTED"
    assert report.errors[labels[4]["id"]] == "not tried: stopped after repeated failures"
    assert report.results == {}


def test_no_calls_mode_scores_only_saved_answers(tmp_path):
    labels = LABELS[:3]
    run(ScriptedLLM(labels[:1]), labels[:1], tmp_path)

    llm = ScriptedLLM(labels)
    report = run(llm, labels, tmp_path, allow_calls=False)

    assert llm.calls == 0
    assert list(report.results) == [labels[0]["id"]]
    assert len(report.errors) == 2
