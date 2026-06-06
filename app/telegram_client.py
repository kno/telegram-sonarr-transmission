import os
import asyncio
import logging
from pyrogram import Client
from app.config import settings
from app.media import extract_media_info, get_media

logger = logging.getLogger(__name__)

_client: Client | None = None
_channel_messages_semaphore = asyncio.Semaphore(2)


def _session_path() -> str:
    return os.path.join(settings.SESSION_DIR, settings.SESSION_NAME)


async def connect_client() -> Client:
    global _client
    _client = Client(
        _session_path(),
        api_id=settings.API_ID,
        api_hash=settings.API_HASH,
    )
    await _client.start()
    me = await _client.get_me()
    logger.info("Telegram connected as %s (@%s)", me.first_name, me.username)

    # Pre-populate peer cache so numeric chat IDs work immediately
    logger.info("Loading dialogs to populate peer cache...")
    count = 0
    async for _ in _client.get_dialogs():
        count += 1
    logger.info("Cached %d dialogs", count)

    return _client


async def disconnect_client():
    global _client
    if _client:
        await _client.stop()
        _client = None


def get_client() -> Client:
    if _client is None:
        raise RuntimeError("Telegram client not initialized")
    return _client


async def get_channel_info(chat_id: int) -> dict:
    """Return metadata for a Telegram channel or group."""
    client = get_client()
    chat = await client.get_chat(chat_id)
    return {
        "id": chat.id,
        "title": chat.title,
        "username": getattr(chat, "username", None),
        "participants_count": (
            getattr(chat, "members_count", None)
            or getattr(chat, "participants_count", None)
        ),
        "description": getattr(chat, "description", None),
    }


def _thumbnail_from_message(message):
    media = get_media(message)
    if not media:
        return None
    thumbs = getattr(media, "thumbs", None)
    if thumbs:
        return thumbs[0]
    return None


def _message_to_channel_item(chat_id: int, message) -> dict | None:
    media_info = extract_media_info(message)
    if not media_info:
        return None
    date = getattr(message, "date", None)
    text = getattr(message, "text", None)
    caption = getattr(message, "caption", None)
    body_parts = [part for part in (text, caption) if part]
    item = {
        "message_id": message.id,
        "date": date.isoformat() if date else None,
        "filename": media_info["filename"],
        "file_size": media_info["size"],
        "mime_type": media_info["mime_type"],
        "media_group_id": getattr(message, "media_group_id", None),
        "text": text,
        "caption": caption,
        "body": "\n\n".join(body_parts) if body_parts else None,
    }
    if _thumbnail_from_message(message):
        item["thumbnail_url"] = f"/api/v2/channels/{chat_id}/messages/{message.id}/thumbnail"
    else:
        item["thumbnail_url"] = None
    return item


async def get_message_thumbnail(chat_id: int, msg_id: int, download_dir: str) -> str | None:
    """Download a Telegram message thumbnail without downloading the full media."""
    client = get_client()
    message = await client.get_messages(chat_id, msg_id)
    thumbnail = _thumbnail_from_message(message)
    if not thumbnail:
        return None
    os.makedirs(download_dir, exist_ok=True)
    try:
        logger.info("Attempting to download thumbnail %s/%d", chat_id, msg_id)
        downloaded_file = await client.download_media(thumbnail, file_name=f"{download_dir}{os.sep}")
        logger.info("Thumbnail downloaded successfully to %s", downloaded_file)
        if not downloaded_file or not os.path.isfile(downloaded_file):
            logger.error("Thumbnail download did not produce a file: %s", downloaded_file)
            return None
        return downloaded_file
    except Exception as e:
        logger.error("Failed to download thumbnail %s/%d: %s", chat_id, msg_id, str(e))
        return None


async def get_channel_messages(
    chat_id: int,
    before: int | None = None,
    around: int | None = None,
    limit: int = 20,
) -> dict:
    """Return downloadable messages from a channel using message-id cursor pagination."""
    client = get_client()
    messages: list[dict] = []
    raw_seen = 0
    async with _channel_messages_semaphore:
        if around is not None:
            found = await client.get_messages(chat_id, around)
            item = _message_to_channel_item(chat_id, found)
            if item:
                messages.append(item)
        history_limit = limit + 1 - len(messages)
        offset_id = around if around is not None else before or 0
        async for message in client.get_chat_history(chat_id, limit=history_limit, offset_id=offset_id):
            raw_seen += 1
            item = _message_to_channel_item(chat_id, message)
            if item:
                messages.append(item)
            if len(messages) > limit:
                break

    has_more = len(messages) > limit or raw_seen > limit
    page = messages[:limit]
    return {
        "messages": page,
        "has_more": has_more,
        "next_cursor": page[-1]["message_id"] if has_more and page else None,
    }
