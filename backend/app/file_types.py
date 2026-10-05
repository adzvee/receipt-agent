"""Detect an uploaded file's real type from its first bytes.

We don't trust the filename or the Content-Type header the browser sends, since either
can be wrong or spoofed.
"""

SUPPORTED_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}


def sniff_mime_type(data: bytes) -> str | None:
    """Return the MIME type for a supported receipt file, or None if unsupported."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    return None
