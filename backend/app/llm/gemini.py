"""Gemini implementation of `LLMClient`, using Google's `google-genai` SDK."""

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.llm.base import Attachment, LLMError, T


class GeminiClient:
    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model
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
        try:
            response = self._get_client().models.generate_content(
                model=self._model, contents=[*parts, prompt], config=config
            )
        except errors.APIError as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc

        if isinstance(response.parsed, response_model):
            return response.parsed
        try:
            return response_model.model_validate_json(response.text or "")
        except ValidationError as exc:
            raise LLMError(f"Gemini returned output that doesn't match the schema: {exc}") from exc
