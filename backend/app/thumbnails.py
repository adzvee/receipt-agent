"""Small previews of receipt photos for the receipts list."""

from io import BytesIO

from PIL import Image, ImageOps

# Twice the size it's shown at, so it stays sharp on high-density screens.
THUMBNAIL_SIZE = (96, 128)


def make_thumbnail(data: bytes) -> bytes:
    """A small JPEG of an image file, upright and on white. Raises OSError if unreadable."""
    with Image.open(BytesIO(data)) as image:
        # For JPEGs, decode at reduced size: much faster for big phone photos.
        image.draft("RGB", THUMBNAIL_SIZE)
        image = ImageOps.exif_transpose(image)  # phone photos are often stored sideways
        image.thumbnail(THUMBNAIL_SIZE)
        flat = Image.new("RGB", image.size, "white")  # JPEG has no transparency
        flat.paste(image, mask=image.getchannel("A") if "A" in image.getbands() else None)
    out = BytesIO()
    flat.save(out, "JPEG", quality=80)
    return out.getvalue()
