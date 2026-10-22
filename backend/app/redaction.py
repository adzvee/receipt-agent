"""Masking full card numbers before anything is saved.

The extraction prompt asks for "brand and last 4 digits" only, but a model can still
return more, and a forwarded email can contain anything. So every piece of text we store
goes through `mask_card_numbers`: a run of 13-19 digits (spaces or dashes allowed) that
passes the Luhn checksum used by all card numbers becomes "•••• 4242".
"""

import re

from app.extraction import ExtractedReceipt

CARD_NUMBER = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")


def passes_luhn(digits: str) -> bool:
    total = 0
    for i, char in enumerate(reversed(digits)):
        n = int(char)
        if i % 2 == 1:  # double every second digit from the right
            n = n * 2 - 9 if n > 4 else n * 2
        total += n
    return total % 10 == 0


def _mask(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    return f"•••• {digits[-4:]}" if passes_luhn(digits) else match.group()


def mask_card_numbers(text: str) -> str:
    return CARD_NUMBER.sub(_mask, text)


def mask_optional(text: str | None) -> str | None:
    return mask_card_numbers(text) if text else text


def redact_extraction(extracted: ExtractedReceipt) -> ExtractedReceipt:
    """A copy with card numbers masked in every text field the model returned."""
    return extracted.model_copy(
        update={
            "vendor": mask_optional(extracted.vendor),
            "payment_method": mask_optional(extracted.payment_method),
            "line_items": [
                item.model_copy(update={"description": mask_card_numbers(item.description)})
                for item in extracted.line_items
            ],
        }
    )
