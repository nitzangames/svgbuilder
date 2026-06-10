"""Small helpers for the engine generator."""

import base64
import os

_MEDIA = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def b64(data):
    """Base64-encode bytes to an ASCII string."""
    return base64.standard_b64encode(data).decode("ascii")


def media_type_for(path):
    """Map an image path's extension to its image/* media type."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in _MEDIA:
        raise ValueError(f"unsupported image type: {ext or '(none)'}")
    return _MEDIA[ext]
