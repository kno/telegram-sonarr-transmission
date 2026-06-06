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


def extract_media_info(message) -> dict | None:
    """Return {filename, size, mime_type} for a message with media, else None."""
    media = get_media(message)
    if not media:
        return None
    return {
        "filename": getattr(media, "file_name", None),
        "size": getattr(media, "file_size", None) or 0,
        "mime_type": getattr(media, "mime_type", None) or "application/octet-stream",
    }
