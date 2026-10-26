"""Run the real extraction over many receipt files, saving each answer as it arrives.

Shared by both evaluations. Saved answers are reused, so a run stopped by a rate limit or
the daily quota resumes where it left off, and re-scoring costs no model calls.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.extraction import ExtractedReceipt, extract_receipt
from app.llm import LLMClient, LLMError

# Two failures in a row usually means a quota or outage, not a problem with one receipt.
MAX_FAILURES_IN_A_ROW = 2


@dataclass(frozen=True)
class Job:
    id: str
    path: Path
    mime_type: str


def short_error(exc: Exception) -> str:
    """The readable start of an error, without the provider's JSON details."""
    return str(exc).split("{")[0].strip(" .")[:200]


def extract_all(
    *,
    llm: LLMClient,
    jobs: list[Job],
    raw_dir: Path,
    refresh: bool = False,
    allow_calls: bool = True,
    delay_seconds: float = 0,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> tuple[dict[str, ExtractedReceipt], dict[str, str]]:
    """Returns (answers by job id, errors by job id). Calls `extract_receipt` directly,
    not the upload endpoint, so the app's per-account daily limits don't apply."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    answers: dict[str, ExtractedReceipt] = {}
    errors: dict[str, str] = {}
    called_before = False
    failures_in_a_row = 0

    for n, job in enumerate(jobs, start=1):
        saved = raw_dir / f"{job.id}.json"
        if saved.exists() and not refresh:
            answers[job.id] = ExtractedReceipt.model_validate_json(saved.read_text())
            continue
        if not allow_calls:
            errors[job.id] = "no saved answer (run without --no-calls)"
            continue
        if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
            errors[job.id] = "not tried: stopped after repeated failures"
            continue

        if called_before and delay_seconds:
            sleep(delay_seconds)  # stay under the free tier's requests-per-minute limit
        called_before = True
        log(f"[{n}/{len(jobs)}] Extracting {job.id}...")
        try:
            answer = extract_receipt(llm, job.path.read_bytes(), job.mime_type)
        except LLMError as exc:
            failures_in_a_row += 1
            errors[job.id] = short_error(exc)
            log(f"  failed: {short_error(exc)}")
            continue
        failures_in_a_row = 0
        saved.write_text(answer.model_dump_json(indent=2) + "\n")
        answers[job.id] = answer
    return answers, errors
