"""Extraction accuracy on WildReceipt, a public set of real receipt photos.

WildReceipt (Sun et al., 2021; hosted by MMOCR) labels every text box on a receipt with a
class such as Store_name_value or Total_value. For each receipt we join the boxes of a
class, in reading order, into one expected value, then normalize it: dates become a set of
possible calendar dates (05/02/18 could be May 2 or Feb 5), amounts become numbers
("Eur154,40" -> 154.40), and names are compared ignoring case, spaces, and punctuation
(the labels have spaces removed: "KOREANRESTAURANT").

    python -m evaluation.wildreceipt --download   # once: ~185 MB into a gitignored folder
    python -m evaluation.wildreceipt              # a fixed sample of 100 test receipts
    python -m evaluation.wildreceipt --all        # all 472

Images and the model's raw answers (which include details like card last-4 digits from
real receipts) stay in the gitignored `evaluation/datasets/` folder. Only the report and a
few failure examples (store names, dates, amounts) are written to `evaluation/results/`.
"""

import argparse
import hashlib
import json
import re
import sys
import tarfile
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path

from app.config import get_settings
from app.extraction import ExtractedReceipt, money, parse_date
from app.llm import LLMClient
from evaluation.extract_all import Job, extract_all

DATASET_URL = "https://download.openmmlab.com/mmocr/data/wildreceipt.tar"
DATASETS_DIR = Path(__file__).parent / "datasets"  # gitignored
DATASET_DIR = DATASETS_DIR / "wildreceipt" / "wildreceipt"
RUNS_DIR = DATASETS_DIR / "wildreceipt-runs"  # raw answers: from real receipts, not committed
RESULTS_DIR = Path(__file__).parent / "results" / "wildreceipt"

DEFAULT_LIMIT = 100
SAMPLE_SEED = "wildreceipt-eval"  # fixes the order, so the first 100 are part of any bigger run

# WildReceipt class ids (class_list.txt) for the values we score. Address is labeled too,
# but the extraction schema has no address field.
LABEL_CLASSES = {1: "store_name", 7: "date", 17: "subtotal", 19: "tax", 21: "tip", 23: "total"}
AMOUNT_FIELDS = ["total", "subtotal", "tax", "tip"]
FIELDS = ["store_name", "date", *AMOUNT_FIELDS]
FIELD_NAMES = {"store_name": "store name"}

# --- Loading ---


@dataclass(frozen=True)
class LabeledReceipt:
    id: str  # the image's file name without extension (a content hash)
    image: Path
    boxes: dict[str, list[str]]  # field -> label texts, in reading order


def reading_order(annotation: dict) -> tuple[int, float]:
    """Top to bottom, then left to right; boxes within half a line count as one row."""
    xs, ys = annotation["box"][0::2], annotation["box"][1::2]
    line_height = max(max(ys) - min(ys), 1)
    return int(min(ys) // (line_height / 2)), min(xs)


def parse_label_line(line: str, dataset_dir: Path = DATASET_DIR) -> LabeledReceipt:
    record = json.loads(line)
    boxes: dict[str, list[str]] = defaultdict(list)
    for annotation in sorted(record["annotations"], key=reading_order):
        name = LABEL_CLASSES.get(annotation["label"])
        if name and annotation["text"].strip():
            boxes[name].append(annotation["text"].strip())
    image = dataset_dir / record["file_name"]
    return LabeledReceipt(id=image.stem, image=image, boxes=dict(boxes))


def load_test_set(dataset_dir: Path = DATASET_DIR) -> list[LabeledReceipt]:
    test_file = dataset_dir / "test.txt"
    if not test_file.exists():
        raise SystemExit(
            f"WildReceipt isn't downloaded ({test_file} is missing). "
            "Run: python -m evaluation.wildreceipt --download"
        )
    return [parse_label_line(line, dataset_dir) for line in test_file.read_text().splitlines()]


def sample(receipts: list[LabeledReceipt], limit: int | None) -> list[LabeledReceipt]:
    """A fixed pseudo-random order, so a 100-receipt run is the start of a full run."""

    def key(receipt: LabeledReceipt) -> str:
        return hashlib.sha256(f"{SAMPLE_SEED}:{receipt.id}".encode()).hexdigest()

    ordered = sorted(receipts, key=key)
    return ordered if limit is None else ordered[:limit]


# --- Normalizing label values ---


def normalize_name(text: str | None) -> str:
    """Uppercase letters and digits only: "Kelly O'Bryan's" -> "KELLYOBRYANS"."""
    if not text:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKC", text).upper() if c.isalnum())


AMOUNT_TOKEN = re.compile(r"(?<![\d.,])[.,]?\d[\d.,]*")


def parse_amount(text: str) -> Decimal | None:
    """The last number in a label, to the cent: "$1,360.00" -> 1360.00, "Eur154,40" ->
    154.40, ".26" -> 0.26. None if there's no number."""
    tokens = AMOUNT_TOKEN.findall(text)
    if not tokens:
        return None
    token = tokens[-1].rstrip(".,")
    if token[0] in ".,":  # ".26"
        token = "0." + token[1:]
    if "," in token and "." in token:  # the later one is the decimal separator
        decimal_sep = "," if token.rfind(",") > token.rfind(".") else "."
        token = token.replace("." if decimal_sep == "," else ",", "").replace(",", ".")
    elif "," in token:  # "154,40" is a decimal comma; "1,360" separates thousands
        whole, _, fraction = token.rpartition(",")
        if len(fraction) == 2:
            token = f"{whole.replace(',', '')}.{fraction}"
        else:
            token = token.replace(",", "")
    elif token.count(".") > 1:  # "1.360.00"
        whole, _, fraction = token.rpartition(".")
        token = f"{whole.replace('.', '')}.{fraction}"
    try:
        return Decimal(token).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None


def amount_candidates(field_name: str, texts: list[str]) -> set[Decimal]:
    """Every amount the label could mean. Repeated boxes (a total printed twice) collapse;
    for tax, several tax lines may also be reported as their sum."""
    amounts = {a for a in map(parse_amount, texts) if a is not None}
    if field_name == "tax" and len(amounts) > 1:
        amounts.add(sum(amounts, Decimal("0")))
    return amounts


MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip
# "0CT": OCR often reads the O as a zero.
MONTH = r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEPT?|[O0]CT|NOV|DEC)[A-Z]*"
SEP = r"[\s\-/.,'´`]*"
YEAR = r"(\d{4}|\d{2})(?!\d)"
DATE_PATTERNS = [
    # 2014-07-22
    ("ymd", re.compile(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)")),
    # 22-JUL-2014, 22JUL14
    ("d_mon_y", re.compile(rf"(?<!\d)(\d{{1,2}}){SEP}{MONTH}{SEP}{YEAR}")),
    # JUL22,2014, Aug15.2017, JAN09'03
    ("mon_d_y", re.compile(rf"{MONTH}{SEP}(\d{{1,2}})(?:ST|ND|RD|TH)?{SEP}{YEAR}")),
    # 12/30/2016, 14/02/18, 07-24-11
    ("numeric", re.compile(r"(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})(?!\d)")),
]


def _year(text: str) -> int:
    if len(text) == 4:
        return int(text)
    return 2000 + int(text) if int(text) <= 35 else 1900 + int(text)  # "95" is 1995


def _month(name: str) -> int:
    return MONTHS[name[:3].replace("0", "O")]


def _valid(year: int, month: int, day: int) -> date | None:
    if not 1980 <= year <= 2035:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def date_candidates(text: str) -> set[date]:
    """Every date a label could mean. "12/30/2016FRI" -> {2016-12-30}; the ambiguous
    "05/02/18" -> {2018-05-02, 2018-02-05}."""
    upper = text.upper()
    found: set[date | None] = set()
    for kind, pattern in DATE_PATTERNS:
        for match in pattern.finditer(upper):
            groups = match.groups()
            if kind == "ymd":
                found.add(_valid(int(groups[0]), int(groups[1]), int(groups[2])))
            elif kind == "d_mon_y":
                found.add(_valid(_year(groups[2]), _month(groups[1]), int(groups[0])))
            elif kind == "mon_d_y":
                found.add(_valid(_year(groups[2]), _month(groups[0]), int(groups[1])))
            else:
                a, b, year = int(groups[0]), int(groups[1]), _year(groups[2])
                found.add(_valid(year, a, b))  # month first (US)
                found.add(_valid(year, b, a))  # day first
        if found - {None}:
            break  # use the most specific pattern that matched
    return {d for d in found if d is not None}


# --- Scoring ---


@dataclass(frozen=True)
class Outcome:
    receipt_id: str
    field: str
    correct: bool
    expected: str  # the joined label text, as printed
    got: str | None
    error: str | None = None  # what kind of mistake, when wrong
    note: str | None = None  # e.g. "close match", "ambiguous date"


def names_match_closely(got: str, texts: list[str]) -> bool:
    """Lenient store-name match: a label box on its own, a close spelling, or one name
    containing the other ("TRADERJOES" in "TRADERJOES552")."""
    candidates = [normalize_name("".join(texts)), *map(normalize_name, texts)]
    for want in filter(None, candidates):
        shorter, longer = sorted([got, want], key=len)
        if got == want or SequenceMatcher(None, got, want).ratio() >= 0.8:
            return True
        if len(shorter) >= 5 and shorter in longer:
            return True
    return False


def score_store_name(receipt_id: str, texts: list[str], got: str | None) -> Outcome:
    joined = "".join(texts)
    if not got:
        return Outcome(receipt_id, "store_name", False, joined, got, "missing")
    if normalize_name(got) == normalize_name(joined):
        return Outcome(receipt_id, "store_name", True, joined, got)
    if names_match_closely(normalize_name(got), texts):
        return Outcome(receipt_id, "store_name", True, joined, got, note="close match")
    return Outcome(receipt_id, "store_name", False, joined, got, "different name")


def score_date(receipt_id: str, texts: list[str], got: str | None) -> Outcome | None:
    candidates = set().union(*(date_candidates(t) for t in texts))
    joined = " ".join(texts)
    if not candidates:
        return None  # a label we can't read, e.g. "FRI"; reported separately
    note = "ambiguous date" if len(candidates) > 1 else None
    if got is None:
        return Outcome(receipt_id, "date", False, joined, got, "missing", note)
    predicted = parse_date(got)
    if predicted is None:
        return Outcome(receipt_id, "date", False, joined, got, "not a valid date", note)
    if predicted in candidates:
        return Outcome(receipt_id, "date", True, joined, got, note=note)
    swapped = _valid(predicted.year, predicted.day, predicted.month)
    if swapped in candidates:
        error = "day and month swapped"
    elif any((c.month, c.day) == (predicted.month, predicted.day) for c in candidates):
        error = "wrong year"
    else:
        error = "different date"
    return Outcome(receipt_id, "date", False, joined, got, error, note)


def _digits(value: Decimal) -> str:
    """The significant digits: 3877.00 and 38.77 both give "3877"."""
    return re.sub(r"\D", "", format(value.normalize(), "f")).strip("0")


def amount_error(
    field_name: str, got: Decimal, expected: set[Decimal], others: dict[str, set[Decimal]]
) -> str:
    """What kind of mistake a wrong amount is, most specific first."""
    for other, amounts in others.items():
        if got in amounts:
            return f"gave the {other} instead"
    for want in expected:
        if _digits(got) == _digits(want):
            return "decimal point misplaced"
        a, b = _digits(got), _digits(want)
        if len(a) == len(b) and sum(x != y for x, y in zip(a, b, strict=True)) == 1:
            return "one digit misread"
    return "different amount"


def score_amount(
    receipt_id: str,
    field_name: str,
    texts: list[str],
    got: float | None,
    others: dict[str, set[Decimal]],
) -> Outcome | None:
    expected = amount_candidates(field_name, texts)
    joined = " ".join(texts)
    if not expected:
        return None
    if got is None:
        return Outcome(receipt_id, field_name, False, joined, None, "missing")
    value = money(got)
    shown = f"{value}" if value is not None else str(got)
    if value in expected:
        return Outcome(receipt_id, field_name, True, joined, shown)
    error = amount_error(field_name, value, expected, others) if value is not None else "invalid"
    return Outcome(receipt_id, field_name, False, joined, shown, error)


def score_receipt(
    receipt: LabeledReceipt, answer: ExtractedReceipt
) -> tuple[list[Outcome], list[str]]:
    """(outcomes for each labeled field, fields whose label couldn't be read)."""
    outcomes: list[Outcome] = []
    unreadable: list[str] = []
    boxes = receipt.boxes
    if "store_name" in boxes:
        outcomes.append(score_store_name(receipt.id, boxes["store_name"], answer.vendor))
    if "date" in boxes:
        outcome = score_date(receipt.id, boxes["date"], answer.purchase_date)
        if outcome:
            outcomes.append(outcome)
        else:
            unreadable.append("date")

    amounts = {f: amount_candidates(f, boxes[f]) for f in AMOUNT_FIELDS if f in boxes}
    for name in AMOUNT_FIELDS:
        if name not in boxes:
            continue
        others = {other: a for other, a in amounts.items() if other != name and a}
        outcome = score_amount(receipt.id, name, boxes[name], getattr(answer, name), others)
        if outcome:
            outcomes.append(outcome)
        else:
            unreadable.append(name)
    return outcomes, unreadable


# --- Report ---


@dataclass
class Report:
    model: str
    planned: int  # receipts in this run
    today: date
    outcomes: list[Outcome] = field(default_factory=list)
    unreadable: Counter = field(default_factory=Counter)  # field -> labels we couldn't parse
    scored_receipts: int = 0
    errors: dict[str, str] = field(default_factory=dict)

    def field_outcomes(self, name: str) -> list[Outcome]:
        return [o for o in self.outcomes if o.field == name]

    def failures(self) -> list[Outcome]:
        return [o for o in self.outcomes if not o.correct]

    def examples(self, per_error: int = 2) -> list[Outcome]:
        """A few failures of each kind, most common kinds first."""
        by_kind: dict[tuple[str, str], list[Outcome]] = defaultdict(list)
        for outcome in self.failures():
            by_kind[(outcome.field, outcome.error or "")].append(outcome)
        ordered = sorted(by_kind.values(), key=len, reverse=True)
        return [o for group in ordered for o in group[:per_error]]

    def to_markdown(self) -> str:
        done = self.scored_receipts
        status = "" if done == self.planned else f" ({done} of {self.planned} so far)"
        lines = [
            f"# WildReceipt extraction accuracy: {self.model}",
            "",
            f"{done} real receipts from the WildReceipt test split{status}, run on {self.today}.",
            "Each field is scored only on receipts where WildReceipt labels it.",
            "",
            "| Field | Accuracy | Correct | Labeled in |",
            "| --- | ---: | ---: | ---: |",
        ]
        for name in FIELDS:
            outcomes = self.field_outcomes(name)
            correct = sum(o.correct for o in outcomes)
            label = FIELD_NAMES.get(name, name)
            lines.append(
                f"| {label} | {percent(correct, len(outcomes))} | {correct}/{len(outcomes)} "
                f"| {len(outcomes)} |"
            )
        stores = self.field_outcomes("store_name")
        exact = sum(o.correct and o.note is None for o in stores)
        ambiguous = [o for o in self.field_outcomes("date") if o.note == "ambiguous date"]
        lines += [
            "",
            f"- Store names: {exact}/{len(stores)} ({percent(exact, len(stores))}) match the "
            "label exactly (ignoring case, spaces, punctuation); the rest of the correct ones "
            "are close matches (a typo, a branch number, or just one of the label's boxes).",
            f"- {len(ambiguous)} dates could be read two ways (e.g. 05/02/18); either reading "
            "counts as correct.",
        ]
        if self.unreadable:
            parts = ", ".join(f"{n} {FIELD_NAMES.get(f, f)}" for f, n in self.unreadable.items())
            lines.append(f"- Labels that couldn't be parsed, so weren't scored: {parts}.")

        lines += [
            "",
            "## Most common errors",
            "",
            "| Field | Error | Count |",
            "| --- | --- | ---: |",
        ]
        kinds = Counter((o.field, o.error) for o in self.failures())
        for (name, error), count in kinds.most_common():
            lines.append(f"| {FIELD_NAMES.get(name, name)} | {error} | {count} |")
        if not kinds:
            lines.append("| | None | 0 |")

        lines += ["", "## Failure examples", ""]
        for o in self.examples():
            lines.append(
                f"- `{o.receipt_id[:12]}` {FIELD_NAMES.get(o.field, o.field)}, {o.error}: "
                f"label `{o.expected}`, model `{o.got}`"
            )
        if self.errors:
            lines += ["", "## Not scored yet", ""]
            reasons = Counter(self.errors.values())
            lines += [f"- {count} receipts: {reason}" for reason, count in reasons.items()]
        return "\n".join(lines) + "\n"


def percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def evaluate(
    *,
    llm: LLMClient,
    model: str,
    receipts: list[LabeledReceipt],
    raw_dir: Path,
    today: date,
    **extract_options,
) -> Report:
    jobs = [Job(r.id, r.image, "image/jpeg") for r in receipts]
    answers, errors = extract_all(llm=llm, jobs=jobs, raw_dir=raw_dir, **extract_options)
    report = Report(model=model, planned=len(receipts), today=today, errors=errors)
    for receipt in receipts:
        if receipt.id not in answers:
            continue
        outcomes, unreadable = score_receipt(receipt, answers[receipt.id])
        report.outcomes += outcomes
        report.unreadable.update(unreadable)
        report.scored_receipts += 1
    return report


# --- Download ---


def download_dataset(datasets_dir: Path = DATASETS_DIR) -> None:
    """Fetch and unpack WildReceipt, refusing any archive entry that isn't a plain file or
    folder inside the target directory."""
    target = datasets_dir / "wildreceipt"
    if (target / "wildreceipt" / "test.txt").exists():
        print(f"Already downloaded: {target}")
        return
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "wildreceipt.tar"
    print(f"Downloading {DATASET_URL} (~185 MB)...")
    urllib.request.urlretrieve(DATASET_URL, archive)
    with tarfile.open(archive) as tar:
        root = target.resolve()
        for member in tar.getmembers():
            path = (target / member.name).resolve()
            if not (member.isfile() or member.isdir()) or not path.is_relative_to(root):
                raise SystemExit(f"Refusing suspicious archive entry: {member.name}")
        tar.extractall(target)
    archive.unlink()
    print(f"Unpacked into {target}")


def main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Extraction accuracy on WildReceipt.")
    parser.add_argument("--download", action="store_true", help="fetch the dataset and exit")
    parser.add_argument("--model", default=settings.gemini_model)
    size = parser.add_mutually_exclusive_group()
    size.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="receipts (default 100)")
    size.add_argument("--all", action="store_true", help="all 472 test receipts")
    parser.add_argument("--refresh", action="store_true", help="ignore saved answers")
    parser.add_argument("--no-calls", action="store_true", help="only score saved answers")
    parser.add_argument("--delay", type=float, default=13, help="seconds between calls")
    args = parser.parse_args(argv)

    if args.download:
        download_dataset()
        return

    from app.llm.gemini import GeminiClient

    receipts = sample(load_test_set(), None if args.all else args.limit)
    print(f"Model: {args.model}. Receipts: {len(receipts)}.")
    report = evaluate(
        llm=GeminiClient(api_key=settings.gemini_api_key, model=args.model),
        model=args.model,
        receipts=receipts,
        raw_dir=RUNS_DIR / args.model,
        today=date.today(),
        refresh=args.refresh,
        allow_calls=not args.no_calls,
        delay_seconds=args.delay,
    )

    out_dir = RESULTS_DIR / args.model
    out_dir.mkdir(parents=True, exist_ok=True)
    name = "all" if args.all else str(len(receipts))
    (out_dir / f"report-{name}.md").write_text(report.to_markdown())
    examples = [asdict(o) for o in report.examples(per_error=3)]
    (out_dir / f"failure-examples-{name}.json").write_text(json.dumps(examples, indent=2) + "\n")
    print(report.to_markdown())
    if report.errors:
        sys.exit(
            f"{len(report.errors)} receipts not scored yet. Run the same command again "
            "(e.g. after the daily quota resets) to continue where it stopped."
        )


if __name__ == "__main__":
    main()
