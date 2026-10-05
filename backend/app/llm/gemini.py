"""Gemini implementation of `LLMClient`, using Google's `google-genai` SDK."""

import logging
import time
from collections.abc import Callable

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


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_attempts: int = 3,
        retry_delay_seconds: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._api_key = api_key
        self._model = model
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleep = sleep  # injectable so tests don't actually wait
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        # Created lazily so the app can start (and tests can run) without an API key.
        if self._client is None:
            if not self._api_key:
                raise LLMError("GEMINI_API_KEY is not set. Add it to the .env file.")
            self._client = genai.Client(api_key=self._api_key)
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
        self, *, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> AssistantMessage:
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=[_to_declaration(t) for t in tools])],
            # We run tools ourselves (see app/agent), so the SDK must not.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0,
        )
        response = self._generate_with_retries(contents=_to_contents(messages), config=config)

        content = response.candidates[0].content if response.candidates else None
        if content is None:
            raise LLMError("Gemini returned an empty response.")
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
        """Call Gemini, retrying temporary failures with exponential backoff (2s, 4s, ...)."""
        client = self._get_client()
        for attempt in range(1, self._max_attempts + 1):
            try:
                return client.models.generate_content(
                    model=self._model, contents=contents, config=config
                )
            except errors.APIError as exc:
                if exc.code not in RETRYABLE_STATUS_CODES or attempt == self._max_attempts:
                    raise LLMError(f"Gemini request failed: {exc}") from exc
                delay = self._retry_delay_seconds * 2 ** (attempt - 1)
                logger.warning(
                    "Gemini returned %s (attempt %d/%d); retrying in %.0fs",
                    exc.code,
                    attempt,
                    self._max_attempts,
                    delay,
                )
                self._sleep(delay)
        raise AssertionError("unreachable")


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
