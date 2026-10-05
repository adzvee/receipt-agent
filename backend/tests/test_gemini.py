from types import SimpleNamespace

import pytest
from google.genai import errors

from app.extraction import ExtractedReceipt
from app.llm import LLMError
from app.llm.gemini import GeminiClient
from tests.factories import make_extracted_receipt


def api_error(code: int) -> errors.APIError:
    error_class = errors.ServerError if code >= 500 else errors.ClientError
    return error_class(code, {"error": {"code": code, "message": "test", "status": "TEST"}})


class FakeGenaiClient:
    """Stands in for `genai.Client`: each call takes the next outcome (an error or a result)."""

    def __init__(self, outcomes: list):
        self.outcomes = outcomes
        self.calls = 0
        self.models = self

    def generate_content(self, **kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(parsed=outcome, text=None)


def make_client(outcomes: list) -> tuple[GeminiClient, FakeGenaiClient, list[float]]:
    sleeps: list[float] = []
    client = GeminiClient(api_key="test-key", model="gemini-test", sleep=sleeps.append)
    fake = FakeGenaiClient(outcomes)
    client._client = fake
    return client, fake, sleeps


def extract(client: GeminiClient) -> ExtractedReceipt:
    return client.generate_structured(prompt="extract", response_model=ExtractedReceipt)


def test_missing_api_key_gives_a_clear_error():
    client = GeminiClient(api_key="", model="gemini-test")

    with pytest.raises(LLMError, match="GEMINI_API_KEY is not set"):
        extract(client)


def test_returns_parsed_response():
    expected = make_extracted_receipt()
    client, fake, sleeps = make_client([expected])

    assert extract(client) == expected
    assert fake.calls == 1
    assert sleeps == []


def test_temporary_error_is_retried_with_backoff():
    expected = make_extracted_receipt()
    client, fake, sleeps = make_client([api_error(503), api_error(429), expected])

    assert extract(client) == expected
    assert fake.calls == 3
    assert sleeps == [2.0, 4.0]


def test_gives_up_after_max_attempts():
    client, fake, sleeps = make_client([api_error(503)] * 3)

    with pytest.raises(LLMError, match="503"):
        extract(client)
    assert fake.calls == 3
    assert sleeps == [2.0, 4.0]


def test_permanent_error_is_not_retried():
    client, fake, sleeps = make_client([api_error(401)])

    with pytest.raises(LLMError, match="401"):
        extract(client)
    assert fake.calls == 1
    assert sleeps == []
