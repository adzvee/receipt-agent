from types import SimpleNamespace

import pytest
from google.genai import errors, types

from app.agent.tools import TOOL_SPECS
from app.extraction import ExtractedReceipt
from app.llm import AssistantMessage, LLMError, ToolCall, ToolResultMessage, UserMessage
from app.llm.gemini import GeminiClient, _to_contents
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
        if isinstance(outcome, types.Content):
            return SimpleNamespace(candidates=[SimpleNamespace(content=outcome)])
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


# --- Chat / tool calling ---


def chat(client: GeminiClient, messages) -> AssistantMessage:
    return client.chat(system="sys", messages=messages, tools=TOOL_SPECS)


def test_chat_returns_tool_calls_and_keeps_original_content():
    model_content = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    id="abc", name="spending_summary", args={"group_by": "month"}
                ),
                thought_signature=b"opaque-signature",
            )
        ],
    )
    client, _, _ = make_client([model_content])

    reply = chat(client, [UserMessage("Spending per month?")])

    assert reply.tool_calls == [
        ToolCall(id="abc", name="spending_summary", arguments={"group_by": "month"})
    ]
    assert reply.text is None
    assert reply.provider_data is model_content


def test_chat_returns_text_answer_without_thoughts():
    model_content = types.Content(
        role="model",
        parts=[
            types.Part(text="thinking about it...", thought=True),
            types.Part(text="You spent $20."),
        ],
    )
    client, _, _ = make_client([model_content])

    reply = chat(client, [UserMessage("How much?")])

    assert reply.text == "You spent $20."
    assert reply.tool_calls == []


def test_to_contents_replays_model_turn_and_groups_tool_results():
    original = types.Content(role="model", parts=[types.Part(text="calling tools")])
    call_a = ToolCall(id="a", name="spending_summary", arguments={})
    call_b = ToolCall(id="b", name="list_receipts", arguments={})

    contents = _to_contents(
        [
            UserMessage("question"),
            AssistantMessage(tool_calls=[call_a, call_b], provider_data=original),
            ToolResultMessage(call=call_a, result={"groups": []}),
            ToolResultMessage(call=call_b, result={"receipts": []}),
            AssistantMessage(text="earlier answer from history"),
        ]
    )

    assert [c.role for c in contents] == ["user", "model", "user", "model"]
    assert contents[1] is original  # sent back exactly, signatures included
    results = contents[2].parts
    assert [(p.function_response.id, p.function_response.name) for p in results] == [
        ("a", "spending_summary"),
        ("b", "list_receipts"),
    ]
    assert contents[3].parts[0].text == "earlier answer from history"
