"""Gemini implementation of `LLMClient`, using Google's `google-genai` SDK."""

import logging
import re
import time
from collections.abc import Callable

import httpx
from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.llm.base import (
    AssistantMessage,
    Attachment,
    ChatMessage,
    LLMError,
    T,
    ToolCall,
    ToolResultMessage,
    ToolSpec,
    UserMessage,
)

logger = logging.getLogger(__name__)

# Errors worth retrying: rate limits (429) and temporary server problems (5xx).
# Anything else, like a bad API key (401), will fail the same way every time.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Without a limit, a request whose reply never arrives waits forever (this froze an
# evaluation run for half an hour). Receipts usually take seconds; 2 minutes is generous.
REQUEST_TIMEOUT_SECONDS = 120.0

# Network problems where trying again may work: no reply in time, or no connection.
TRANSIENT_NETWORK_ERRORS = (httpx.TimeoutException, httpx.ConnectError)

# Google sometimes says how long to wait. Per-minute rate limits ask for under a minute,
# which is worth waiting for. Daily quotas ask for hours, which no retry can fix.
MAX_WAIT_SECONDS = 60.0


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_attempts: int = 3,
        retry_delay_seconds: float = 2.0,
        max_wait_seconds: float = MAX_WAIT_SECONDS,
        timeout_seconds: float = REQUEST_TIMEOUT_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._api_key = api_key
        self._model = model
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._max_wait_seconds = max_wait_seconds
        self._timeout_seconds = timeout_seconds
        self._sleep = sleep  # injectable so tests don't actually wait
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        # Created lazily so the app can start (and tests can run) without an API key.
        if self._client is None:
            if not self._api_key:
                raise LLMError("GEMINI_API_KEY is not set. Add it to the .env file.")
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(timeout=int(self._timeout_seconds * 1000)),  # ms
            )
        return self._client

    def generate_structured(
        self,
        *,
        prompt: str,
        response_model: type[T],
        attachments: list[Attachment] | None = None,
    ) -> T:
        parts = [
            types.Part.from_bytes(data=a.data, mime_type=a.mime_type) for a in attachments or []
        ]
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_model,
            temperature=0,
        )
        response = self._generate_with_retries(contents=[*parts, prompt], config=config)

        if isinstance(response.parsed, response_model):
            return response.parsed
        try:
            return response_model.model_validate_json(response.text or "")
        except ValidationError as exc:
            raise LLMError(f"Gemini returned output that doesn't match the schema: {exc}") from exc

    def chat(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        allow_tool_calls: bool = True,
    ) -> AssistantMessage:
        config = types.GenerateContentConfig(
            system_instruction=system,
            # The tools stay declared even when calls aren't allowed, because earlier turns
            # in `messages` refer to them.
            tools=[types.Tool(function_declarations=[_to_declaration(t) for t in tools])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="AUTO" if allow_tool_calls else "NONE"
                )
            ),
            # We run tools ourselves (see app/agent), so the SDK must not.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0,
        )
        response = self._generate_with_retries(contents=_to_contents(messages), config=config)

        candidate = response.candidates[0] if response.candidates else None
        content = candidate.content if candidate else None
        if content is None or not content.parts:
            # e.g. a blocked reply, or MALFORMED_FUNCTION_CALL. Say so, rather than letting
            # it look like an empty answer.
            reason = candidate.finish_reason if candidate else "no candidates"
            raise LLMError(f"Gemini returned no reply (finish reason: {reason}).")
        parts = content.parts or []
        text = "".join(p.text for p in parts if p.text and not p.thought) or None
        tool_calls = [
            ToolCall(
                id=p.function_call.id,
                name=p.function_call.name or "",
                arguments=dict(p.function_call.args or {}),
            )
            for p in parts
            if p.function_call
        ]
        return AssistantMessage(text=text, tool_calls=tool_calls, provider_data=content)

    def _generate_with_retries(
        self, *, contents: list, config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        """Call Gemini, retrying temporary failures (see `_retry_delay`)."""
        client = self._get_client()
        for attempt in range(1, self._max_attempts + 1):
            try:
                return client.models.generate_content(
                    model=self._model, contents=contents, config=config
                )
            except errors.APIError as exc:
                delay = self._retry_delay(exc, attempt)
                if delay is None or attempt == self._max_attempts:
                    raise LLMError(f"Gemini request failed: {exc}") from exc
                logger.warning(
                    "Gemini returned %s (attempt %d/%d); retrying in %.0fs",
                    exc.code,
                    attempt,
                    self._max_attempts,
                    delay,
                )
                self._sleep(delay)
            except TRANSIENT_NETWORK_ERRORS as exc:
                problem = (
                    f"no reply within {self._timeout_seconds:.0f}s"
                    if isinstance(exc, httpx.TimeoutException)
                    else "couldn't connect"
                )
                if attempt == self._max_attempts:
                    raise LLMError(f"Gemini request failed: {problem}") from exc
                delay = self._retry_delay_seconds * 2 ** (attempt - 1)
                logger.warning(
                    "Gemini request failed: %s (attempt %d/%d); retrying in %.0fs",
                    problem,
                    attempt,
                    self._max_attempts,
                    delay,
                )
                self._sleep(delay)
        raise AssertionError("unreachable")

    def _retry_delay(self, exc: errors.APIError, attempt: int) -> float | None:
        """Seconds to wait before retrying, or None if retrying won't help."""
        if exc.code not in RETRYABLE_STATUS_CODES:
            return None
        suggested = suggested_retry_delay(exc)
        if suggested is None:
            return self._retry_delay_seconds * 2 ** (attempt - 1)  # 2s, 4s, ...
        if suggested > self._max_wait_seconds:
            return None
        return suggested + 1  # Google rounds the suggestion down


def suggested_retry_delay(exc: errors.APIError) -> float | None:
    """Google's "retry after N seconds" hint, from the RetryInfo entry in the error body.

    e.g. {"error": {"details": [{"@type": ".../google.rpc.RetryInfo", "retryDelay": "29s"}]}}
    """
    body = exc.details if isinstance(exc.details, dict) else {}
    for detail in body.get("error", {}).get("details", []):
        if isinstance(detail, dict) and detail.get("@type", "").endswith("google.rpc.RetryInfo"):
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    return None


def _to_declaration(tool: ToolSpec) -> types.FunctionDeclaration:
    return types.FunctionDeclaration(
        name=tool.name,
        description=tool.description,
        parameters_json_schema=tool.parameters.model_json_schema(),
    )


def _to_contents(messages: list[ChatMessage]) -> list[types.Content]:
    """Convert our provider-neutral messages into Gemini's format."""
    contents: list[types.Content] = []
    for message in messages:
        match message:
            case UserMessage(text=text):
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
            case AssistantMessage(provider_data=types.Content() as original):
                contents.append(original)  # replay exactly, including any thought signatures
            case AssistantMessage(text=text):
                # e.g. earlier answers in the chat history sent back by the frontend
                contents.append(
                    types.Content(role="model", parts=[types.Part.from_text(text=text or "")])
                )
            case ToolResultMessage(call=call, result=result):
                part = types.Part(
                    function_response=types.FunctionResponse(
                        id=call.id, name=call.name, response=result
                    )
                )
                # All results for one model turn go back together in a single message.
                previous = contents[-1] if contents else None
                if previous and previous.parts and previous.parts[0].function_response:
                    previous.parts.append(part)
                else:
                    contents.append(types.Content(role="user", parts=[part]))
    return contents
