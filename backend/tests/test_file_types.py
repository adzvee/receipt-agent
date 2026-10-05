import pytest

from app.file_types import sniff_mime_type
from tests.fakes import JPEG_BYTES, PDF_BYTES, PNG_BYTES, WEBP_BYTES


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (JPEG_BYTES, "image/jpeg"),
        (PNG_BYTES, "image/png"),
        (WEBP_BYTES, "image/webp"),
        (PDF_BYTES, "application/pdf"),
        (b"GIF89a" + b"\x00" * 10, None),
        (b"just some text", None),
        (b"", None),
    ],
)
def test_sniff_mime_type(data, expected):
    assert sniff_mime_type(data) == expected
