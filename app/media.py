"""Helpers for extracting media metadata from Telegram messages.

Telegram messages carry their file in different attributes depending on how
the sender uploaded it: `document` for "send as file", `video` for native
video uploads, `audio` for music, and `photo` for images. All expose enough
metadata for the rest of the pipeline to treat them uniformly.
"""


def get_media(message):
    """Return the message's downloadable media object, or None."""
    if message is None:
        return None
    for attr in ("document", "video", "audio", "photo"):
        media = getattr(message, attr, None)
        if media:
            return media
    return None


def _media_attr(media, *attrs, value_type=None):
    for attr in attrs:
        value = getattr(media, attr, None)
        if value is not None and (value_type is None or isinstance(value, value_type)):
            return value
    file_info = getattr(media, "file", None)
    if file_info is not None:
        for attr in attrs:
            value = getattr(file_info, attr, None)
            if value is not None and (value_type is None or isinstance(value, value_type)):
                return value
    return None


def extract_media_info(message) -> dict | None:
    """Return {filename, size, mime_type} for a message with media, else None."""
    media = get_media(message)
    if not media:
        return None
    return {
        "filename": _media_attr(media, "file_name", "name", value_type=str),
        "size": _media_attr(media, "file_size", "size", value_type=int) or 0,
        "mime_type": _media_attr(media, "mime_type", value_type=str) or "application/octet-stream",
    }
