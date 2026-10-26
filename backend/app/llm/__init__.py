"""Provider-agnostic LLM interface. The rest of the app depends only on `LLMClient`."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import get_settings
from app.llm.base import (
    AssistantMessage,
    Attachment,
    ChatMessage,
    LLMClient,
    LLMError,
    TokenUsage,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)

__all__ = [
    "AssistantMessage",
    "Attachment",
    "ChatMessage",
    "LLMClient",
    "LLMDep",
    "LLMError",
    "ToolCall",
    "ToolResultMessage",
    "TokenUsage",
    "ToolSpec",
    "UserMessage",
    "get_llm",
]


@lru_cache
def get_llm() -> LLMClient:
    """FastAPI dependency returning the configured LLM client. Tests override this."""
    from app.llm.gemini import GeminiClient

    settings = get_settings()
    return GeminiClient(api_key=settings.gemini_api_key, model=settings.gemini_model)


LLMDep = Annotated[LLMClient, Depends(get_llm)]
