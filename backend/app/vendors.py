"""Comparing vendor names, which are printed inconsistently ("STARBUCKS #1234", "Starbucks")."""

import re
from difflib import SequenceMatcher

# Words that don't help tell businesses apart.
_NOISE_WORDS = {"the", "inc", "llc", "ltd", "co", "corp", "store", "shop"}

SIMILARITY_THRESHOLD = 0.85


def normalize_vendor(name: str | None) -> str | None:
    """Lowercase, drop punctuation, store numbers, and noise words.

    "The Corner Café, Inc. #42" -> "corner café"
    """
    if not name:
        return None
    words = re.sub(r"[^\w\s]", " ", name.lower()).split()
    kept = [w for w in words if w not in _NOISE_WORDS and not w.isdigit()]
    return " ".join(kept) or None


def vendors_match(a: str | None, b: str | None) -> bool:
    """True if two vendor names very likely refer to the same business."""
    key_a, key_b = normalize_vendor(a), normalize_vendor(b)
    if not key_a or not key_b:
        return False
    return key_a == key_b or SequenceMatcher(None, key_a, key_b).ratio() >= SIMILARITY_THRESHOLD
