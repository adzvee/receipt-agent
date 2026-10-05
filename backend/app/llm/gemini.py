"""Gemini implementation of `LLMClient`, using Google's `google-genai` SDK."""

import logging
import time
from collections.abc import Callable

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.llm.base import Attachment, LLMError, T

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
