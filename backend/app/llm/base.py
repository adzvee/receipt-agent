"""The interface every LLM provider must implement.

Swapping Gemini for another provider means writing one new class with these methods;
nothing else in the app has to change.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Attachment:
    """A file sent to the model alongside the prompt (e.g. a receipt image or PDF)."""

    data: bytes
    mime_type: str


class LLMError(Exception):
    """Raised when the provider fails or returns output we can't use."""


# --- Tool calling ---


@dataclass(frozen=True)
class ToolSpec:
    """A function the model may ask us to run. `parameters` defines its arguments."""

    name: str
    description: str
    parameters: type[BaseModel]


@dataclass(frozen=True)
class ToolCall:
    id: str | None  # the provider's id for this call, if it assigns one
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class AssistantMessage:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # The provider's original response, replayed as-is on the next turn. Some models
    # (e.g. Gemini 3) attach signatures to tool calls that must be sent back unchanged.
    provider_data: Any = None


@dataclass(frozen=True)
class ToolResultMessage:
    call: ToolCall
    result: dict[str, Any]


ChatMessage = UserMessage | AssistantMessage | ToolResultMessage


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

    def chat(
        self, *, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AssistantMessage:
        """One model turn: returns either a final text answer or tool calls to run.

        The caller runs any requested tools and calls `chat` again with the results.
        """
        ...
