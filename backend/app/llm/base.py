"""The interface every LLM provider must implement.

Swapping Gemini for another provider means writing one new class with these methods;
nothing else in the app has to change.
"""

from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Attachment:
    """A file sent to the model alongside the prompt (e.g. a receipt image or PDF)."""

    data: bytes
    mime_type: str


class LLMError(Exception):
    """Raised when the provider fails or returns output we can't use."""


class LLMClient(Protocol):
    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[T],
        attachments: list[Attachment] | None = None,
    ) -> T:
        """Ask the model for output that conforms to `response_model` and return it parsed."""
        ...
