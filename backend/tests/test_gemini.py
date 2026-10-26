from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors, types

from app.agent.tools import TOOL_SPECS
from app.extraction import ExtractedReceipt
from app.llm import AssistantMessage, LLMError, TokenUsage, ToolCall, ToolResultMessage, UserMessage
from app.llm.gemini import GeminiClient, _to_contents, suggested_retry_delay
from tests.factories import make_extracted_receipt


def api_error(code: int, retry_delay: str | None = None) -> errors.APIError:
    """A Gemini SDK error, optionally carrying Google's "retry after" hint."""
    error = {"code": code, "message": "test", "status": "TEST"}
    if retry_delay is not None:
        error["details"] = [
            {"@type": "type.googleapis.com/google.rpc.Help", "links": []},
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay},
        ]
    error_class = errors.ServerError if code >= 500 else errors.ClientError
    return error_class(code, {"error": error})


class FakeGenaiClient:
    """Stands in for `genai.Client`: each call takes the next outcome (an error or a result)."""

    def __init__(self, outcomes: list):
        self.outcomes = outcomes
        self.calls = 0
        self.last_request: dict = {}
        self.models = self

    def generate_content(self, **kwargs):
        self.calls += 1
        self.last_request = kwargs
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, types.Content):
            return SimpleNamespace(candidates=[SimpleNamespace(content=outcome)])
        if isinstance(outcome, types.Candidate):
            return SimpleNamespace(candidates=[outcome])
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


def test_short_suggested_wait_is_followed():
    # e.g. a per-minute rate limit: "Please retry in 29.45s"
    expected = make_extracted_receipt()
    client, fake, sleeps = make_client([api_error(429, retry_delay="29s"), expected])

    assert extract(client) == expected
    assert sleeps == [30.0]  # Google rounds down, so we add a second


def test_long_suggested_wait_is_not_retried():
    # e.g. a daily quota: "Please retry in 21h36m"
    client, fake, sleeps = make_client([api_error(429, retry_delay="77769s")])

    with pytest.raises(LLMError, match="429"):
        extract(client)
    assert fake.calls == 1
    assert sleeps == []


def test_suggested_retry_delay_parsing():
    assert suggested_retry_delay(api_error(429, retry_delay="29s")) == 29.0
    assert suggested_retry_delay(api_error(429, retry_delay="1.5s")) == 1.5
    assert suggested_retry_delay(api_error(429, retry_delay="soon")) is None
    assert suggested_retry_delay(api_error(503)) is None


def test_token_usage_of_the_last_call_is_recorded():
    client, fake, _ = make_client([make_extracted_receipt()])
    response = SimpleNamespace(
        parsed=make_extracted_receipt(),
        text=None,
        usage_metadata=SimpleNamespace(
            prompt_token_count=1290, candidates_token_count=210, thoughts_token_count=400
        ),
    )
    fake.generate_content = lambda **kwargs: response

    extract(client)

    assert client.last_usage == TokenUsage(
        input_tokens=1290, output_tokens=610, thinking_tokens=400
    )


def test_requests_have_a_time_limit():
    client = GeminiClient(api_key="test-key", model="gemini-test", timeout_seconds=90)

    sdk_client = client._get_client()

    assert sdk_client._api_client._http_options.timeout == 90_000  # milliseconds


def test_a_request_with_no_reply_is_retried():
    response = make_extracted_receipt()
    client, fake, sleeps = make_client([httpx.ReadTimeout("no reply"), response])

    assert extract(client) == response
    assert fake.calls == 2
    assert sleeps == [2.0]


def test_repeated_timeouts_become_an_llm_error_instead_of_hanging():
    timeouts = [httpx.ReadTimeout("no reply")] * 3
    client, fake, _ = make_client(timeouts)

    with pytest.raises(LLMError, match="no reply within 120s"):
        extract(client)
    assert fake.calls == 3


def test_connection_failures_are_retried_too():
    client, _, _ = make_client([httpx.ConnectError("offline")] * 3)

    with pytest.raises(LLMError, match="couldn't connect"):
        extract(client)


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


def test_chat_can_forbid_tool_calls_while_keeping_tools_declared():
    client, fake, _ = make_client([types.Content(role="model", parts=[types.Part(text="Done.")])])

    client.chat(system="sys", messages=[UserMessage("Q")], tools=TOOL_SPECS, allow_tool_calls=False)

    config = fake.last_request["config"]
    assert config.tool_config.function_calling_config.mode == "NONE"
    assert len(config.tools[0].function_declarations) == len(TOOL_SPECS)


def test_chat_reply_without_parts_is_an_error_not_an_empty_answer():
    malformed = types.Candidate(
        content=types.Content(role="model", parts=[]),
        finish_reason=types.FinishReason.MALFORMED_FUNCTION_CALL,
    )
    client, _, _ = make_client([malformed])

    with pytest.raises(LLMError, match="MALFORMED_FUNCTION_CALL"):
        chat(client, [UserMessage("How much?")])


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
