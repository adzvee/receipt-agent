"""Test doubles, so tests never call a real LLM or need an API key."""

from pydantic import BaseModel

from app.llm import LLMError


class FakeLLM:
    """Returns a canned response (or raises an error) and records what it was asked."""

    def __init__(self, response: BaseModel | None = None, error: str | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def generate_structured(self, *, prompt, response_model, attachments=None):
        self.calls.append(
            {"prompt": prompt, "response_model": response_model, "attachments": attachments or []}
        )
        if self.error:
            raise LLMError(self.error)
        assert isinstance(self.response, response_model)
        return self.response


# Minimal valid file headers; the bytes after them don't matter because the LLM is faked.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
PDF_BYTES = b"%PDF-1.7\n" + b"\x00" * 64
