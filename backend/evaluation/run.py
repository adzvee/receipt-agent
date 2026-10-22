"""Run the real extraction on the labeled samples and report per-field accuracy.

    python -m evaluation.run                     # the model in GEMINI_MODEL
    python -m evaluation.run --model gemini-3.8-flash
    python -m evaluation.run --only cafe_us_date no_date

Each model's raw answers are saved under evaluation/results/<model>/raw/, and reused on
the next run, so a run stopped by rate limits picks up where it left off (and re-scoring
after a change to the scoring costs nothing). --refresh asks the model again, and
--no-calls only scores the answers already saved.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from app.config import get_settings
from app.extraction import ExtractedReceipt, extract_receipt
from app.llm import LLMClient, LLMError
from evaluation.samples import LABELS_FILE, SAMPLES_DIR
from evaluation.scoring import FIELDS, FieldResult, ItemCounts, score_sample

RESULTS_DIR = Path(__file__).parent / "results"

# Two failures in a row usually means a quota or outage, not a problem with one receipt.
MAX_FAILURES_IN_A_ROW = 2


@dataclass
class Report:
    model: str
    today: date
    results: dict[str, list[FieldResult]] = field(default_factory=dict)  # by sample id
    items: list[ItemCounts] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)  # samples the model call failed for

    def accuracy(self, name: str) -> tuple[int, int]:
        """(correct, total) for one field across all scored samples."""
        scores = [r.correct for sample in self.results.values() for r in sample if r.field == name]
        return sum(scores), len(scores)

    def to_markdown(self) -> str:
        scored = len(self.results)
        lines = [
            f"# Extraction accuracy: {self.model}",
            "",
            f"{scored} fake receipts from `evaluation/samples/`, run on {self.today}.",
            "",
            "| Field | Accuracy | Correct |",
            "| --- | ---: | ---: |",
        ]
        for name in FIELDS:
            correct, total = self.accuracy(name)
            lines.append(f"| {name} | {percent(correct, total)} | {correct}/{total} |")

        perfect = sum(all(r.correct for r in sample) for sample in self.results.values())
        matched = sum(c.matched for c in self.items)
        expected = sum(c.expected for c in self.items)
        returned = sum(c.extracted for c in self.items)
        lines += [
            "",
            f"- Receipts with every field right: **{perfect}/{scored}** "
            f"({percent(perfect, scored)})",
            f"- Line items found: {matched}/{expected} ({percent(matched, expected)}); "
            f"of the items returned, {matched}/{returned} were real "
            f"({percent(matched, returned)})",
        ]
        if self.errors:
            lines += ["", "## Not scored", ""]
            lines += [f"- `{sample}`: {error}" for sample, error in self.errors.items()]

        lines += ["", "## Mistakes", ""]
        mistakes = [
            f"- `{sample}` {r.field}: expected `{r.expected}`, got `{r.actual}`"
            for sample, results in self.results.items()
            for r in results
            if not r.correct
        ]
        lines += mistakes or ["None."]
        return "\n".join(lines) + "\n"


def short_error(exc: Exception) -> str:
    """The readable start of an error, without the provider's JSON details."""
    return str(exc).split("{")[0].strip(" .")[:200]


def percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def load_labels(only: list[str] | None = None) -> list[dict]:
    labels = json.loads(LABELS_FILE.read_text())
    if only:
        unknown = set(only) - {label["id"] for label in labels}
        if unknown:
            raise SystemExit(f"Unknown sample(s): {', '.join(sorted(unknown))}")
        labels = [label for label in labels if label["id"] in only]
    return labels


def evaluate(
    *,
    llm: LLMClient,
    model: str,
    labels: list[dict],
    samples_dir: Path = SAMPLES_DIR,
    raw_dir: Path,
    today: date,
    refresh: bool = False,
    allow_calls: bool = True,
    delay_seconds: float = 0,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> Report:
    report = Report(model=model, today=today)
    raw_dir.mkdir(parents=True, exist_ok=True)
    called_before = False
    failures_in_a_row = 0

    for label in labels:
        cached = raw_dir / f"{label['id']}.json"
        if cached.exists() and not refresh:
            extraction = ExtractedReceipt.model_validate_json(cached.read_text())
        elif not allow_calls:
            report.errors[label["id"]] = "no saved answer (run without --no-calls)"
            continue
        elif failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
            report.errors[label["id"]] = "not tried: stopped after repeated failures"
            continue
        else:
            if called_before and delay_seconds:
                sleep(delay_seconds)  # stay under the free tier's requests-per-minute limit
            called_before = True
            log(f"Extracting {label['id']}...")
            data = (samples_dir / label["file"]).read_bytes()
            try:
                extraction = extract_receipt(llm, data, label["mime_type"])
            except LLMError as exc:
                failures_in_a_row += 1
                report.errors[label["id"]] = short_error(exc)
                log(f"  failed: {short_error(exc)}")
                continue
            failures_in_a_row = 0
            cached.write_text(extraction.model_dump_json(indent=2) + "\n")

        results, items = score_sample(label, extraction, today)
        report.results[label["id"]] = results
        report.items.append(items)
    return report


def main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--model", default=settings.gemini_model)
    parser.add_argument("--only", nargs="+", metavar="SAMPLE_ID", help="run just these samples")
    parser.add_argument("--refresh", action="store_true", help="ignore saved answers")
    parser.add_argument(
        "--no-calls", action="store_true", help="only score saved answers; no model calls"
    )
    parser.add_argument(
        "--delay", type=float, default=13, help="seconds between model calls (default: 13)"
    )
    args = parser.parse_args(argv)

    from app.llm.gemini import GeminiClient

    llm = GeminiClient(api_key=settings.gemini_api_key, model=args.model)
    out_dir = RESULTS_DIR / args.model
    report = evaluate(
        llm=llm,
        model=args.model,
        labels=load_labels(args.only),
        raw_dir=out_dir / "raw",
        today=date.today(),
        refresh=args.refresh,
        allow_calls=not args.no_calls,
        delay_seconds=args.delay,
    )
    markdown = report.to_markdown()
    if not args.only:  # a partial run would overwrite the full report with a subset
        (out_dir / "report.md").write_text(markdown)
    print(markdown)
    if report.errors:
        sys.exit(f"{len(report.errors)} sample(s) not scored; run again to retry just those.")


if __name__ == "__main__":
    main()
