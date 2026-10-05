"""Detect an uploaded file's real type from its first bytes.

We don't trust the filename or the Content-Type header the browser sends, since either
can be wrong or spoofed.
"""

# Types users can upload. Detected from the file's bytes by `sniff_mime_type`.
UPLOAD_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

# Everything we store. Plain text is only created by the app itself, for receipts that
# arrive in an email body (stored as text, never HTML, so it can't run in a browser).
FILE_EXTENSIONS = {**UPLOAD_EXTENSIONS, "text/plain": ".txt"}


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
