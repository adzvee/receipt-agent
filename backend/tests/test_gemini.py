import pytest

from app.extraction import ExtractedReceipt
from app.llm import LLMError
from app.llm.gemini import GeminiClient


def test_missing_api_key_gives_a_clear_error():
    client = GeminiClient(api_key="", model="gemini-test")

    with pytest.raises(LLMError, match="GEMINI_API_KEY is not set"):
        client.generate_structured(prompt="hi", response_model=ExtractedReceipt)
