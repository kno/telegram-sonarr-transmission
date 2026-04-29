"""Helpers for extracting media metadata from Telegram messages.

Telegram messages carry their file in different attributes depending on how
the sender uploaded it: `document` for "send as file", `video` for native
video uploads. Both expose `file_name`, `file_size`, `mime_type` so the rest
of the pipeline can treat them uniformly.
"""


def get_media(message):
    """Return the message's media object (document or video), or None."""
    if message is None:
        return None
    doc = getattr(message, "document", None)
    if doc:
        return doc
    video = getattr(message, "video", None)
    if video:
        return video
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
