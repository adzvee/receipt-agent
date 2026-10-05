"""Provider-agnostic LLM interface. The rest of the app depends only on `LLMClient`."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import get_settings
from app.llm.base import Attachment, LLMClient, LLMError

__all__ = ["Attachment", "LLMClient", "LLMDep", "LLMError", "get_llm"]


@lru_cache
def get_llm() -> LLMClient:
    """FastAPI dependency returning the configured LLM client. Tests override this."""
    from app.llm.gemini import GeminiClient

    settings = get_settings()
    return GeminiClient(api_key=settings.gemini_api_key, model=settings.gemini_model)


LLMDep = Annotated[LLMClient, Depends(get_llm)]
