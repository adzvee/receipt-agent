"""Test doubles, so tests never call a real LLM or need an API key."""

from pydantic import BaseModel

from app.llm import LLMError


class FakeLLM:
    """Returns a canned response per response model, and records what it was asked.

    `responses` maps a response model (e.g. ExtractedReceipt) to either the object to
    return or an LLMError to raise.
    """

    def __init__(self, responses: dict[type[BaseModel], BaseModel | LLMError]):
        self.responses = responses
        self.calls: list[dict] = []

    def generate_structured(self, *, prompt, response_model, attachments=None):
        self.calls.append(
            {"prompt": prompt, "response_model": response_model, "attachments": attachments or []}
        )
        response = self.responses[response_model]
        if isinstance(response, LLMError):
            raise response
        return response

    def calls_for(self, response_model: type[BaseModel]) -> list[dict]:
        return [c for c in self.calls if c["response_model"] is response_model]


# Minimal valid file headers; the bytes after them don't matter because the LLM is faked.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64
PDF_BYTES = b"%PDF-1.7\n" + b"\x00" * 64


def unique_png(n: int) -> bytes:
    """A PNG-looking file with different bytes, so it isn't treated as a re-upload."""
    return PNG_BYTES + str(n).encode()
