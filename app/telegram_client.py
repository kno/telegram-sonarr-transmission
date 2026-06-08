import os
import asyncio
import logging
from types import SimpleNamespace

try:
    from telethon import TelegramClient
except ImportError:  # pragma: no cover - dependency is installed in runtime images
    TelegramClient = None

from app.config import settings
from app.media import extract_media_info, get_media

logger = logging.getLogger(__name__)

ONE_MIB = 1024 * 1024

_client: "TelegramAdapter | None" = None
_channel_messages_semaphore = asyncio.Semaphore(2)
_PYROGRAM_UNLOADED = object()
PyrogramClient = _PYROGRAM_UNLOADED


def _telethon_session_name(session_name: str) -> str:
    return session_name if session_name.endswith("_telethon") else f"{session_name}_telethon"


def _session_path() -> str:
    return os.path.join(settings.SESSION_DIR, _telethon_session_name(settings.SESSION_NAME))


def _pyrogram_session_file() -> str:
    return os.path.join(settings.SESSION_DIR, f"{settings.SESSION_NAME}.session")


class DownloadTelegramMessage:
    """Marker wrapper for messages fetched through the download backend."""

    def __init__(self, raw_message):
        self.raw = raw_message

    def __getattr__(self, name):
        return getattr(self.raw, name)


class TelegramMedia:
    """Small media wrapper exposing the attributes consumed by the app."""

    def __init__(self, raw_media, file_info=None):
        self.raw = raw_media
        self.file_name = _string_attr(file_info, "name") or _string_attr(raw_media, "file_name")
        self.file_size = _int_attr(file_info, "size") or _int_attr(raw_media, "file_size") or 0
        self.mime_type = (
            _string_attr(file_info, "mime_type")
            or _string_attr(raw_media, "mime_type")
            or "application/octet-stream"
        )
        self.thumbs = list(getattr(raw_media, "thumbs", None) or [])


class TelegramMessage:
    """Compatibility wrapper for Telethon messages."""

    def __init__(self, raw_message):
        self.raw = raw_message
        self.id = getattr(raw_message, "id", None)
        message_text = getattr(raw_message, "message", None) or getattr(raw_message, "text", None)
        self.text = message_text
        self.caption = message_text
        self.date = getattr(raw_message, "date", None)
        self.chat = getattr(raw_message, "chat", None) or getattr(raw_message, "peer_id", None)
        self.from_user = getattr(raw_message, "sender", None)
        self.sender_chat = None
        self.empty = raw_message is None or bool(getattr(raw_message, "empty", False))
        self.media_group_id = getattr(raw_message, "grouped_id", None)
        self.web_page = getattr(raw_message, "web_preview", None) or getattr(raw_message, "web_page", None)
        self.reply_to_top_message_id = getattr(raw_message, "reply_to_top_id", None)
        self.reply_to_message_id = getattr(raw_message, "reply_to_msg_id", None)
        self.message_thread_id = None
        self.topic_id = None
        self.reply_to_message = None

        media = self._wrap_media(raw_message)
        self.document = media
        self.video = None
        self.audio = None
        self.photo = None
        if media and media.mime_type.startswith("video/"):
            self.video = media
        elif media and media.mime_type.startswith("audio/"):
            self.audio = media
        elif media and media.mime_type.startswith("image/"):
            self.photo = media
            self.document = None

    @staticmethod
    def _wrap_media(raw_message):
        raw_media = getattr(raw_message, "media", None)
        file_info = getattr(raw_message, "file", None)
        if file_info:
            return TelegramMedia(raw_media or file_info, file_info)
        if not raw_media or not _raw_media_has_file_metadata(raw_media):
            return None
        return TelegramMedia(raw_media, None)


class PyrogramDownloadBackend:
    """Narrow Pyrogram backend used only for high-throughput media paths."""

    def __init__(self):
        self.client = None
        self._start_lock = asyncio.Lock()

    async def start(self):
        if self.client is not None:
            return self.client
        async with self._start_lock:
            if self.client is not None:
                return self.client
            pyrogram_client = _load_pyrogram_client()
            if PyrogramClient is None:
                raise RuntimeError("Pyrogram download backend is not installed; install pyrogram and tgcrypto")
            session_file = _pyrogram_session_file()
            if not os.path.exists(session_file):
                raise RuntimeError(
                    "Pyrogram download session not found at "
                    f"{session_file}. Run auth with --backend pyrogram or restore the legacy session."
                )
            client = pyrogram_client(
                settings.SESSION_NAME,
                api_id=settings.API_ID,
                api_hash=settings.API_HASH,
                workdir=settings.SESSION_DIR,
            )
            await client.start()
            self.client = client
            return self.client

    async def stop(self):
        if self.client is not None:
            await self.client.stop()
            self.client = None

    async def get_messages(self, chat_id: int, msg_id: int):
        client = await self.start()
        try:
            message = await client.get_messages(chat_id, msg_id)
        except Exception as exc:
            _raise_timeout_for_flood_wait(exc)
            raise
        return DownloadTelegramMessage(message)

    async def download_media(self, message, file_name: str):
        client = await self.start()
        raw = message.raw if isinstance(message, DownloadTelegramMessage) else message
        try:
            return await client.download_media(raw, file_name=file_name)
        except Exception as exc:
            _raise_timeout_for_flood_wait(exc)
            raise

    def stream_media(self, message, offset: int = 0):
        async def _iterate():
            client = await self.start()
            raw = message.raw if isinstance(message, DownloadTelegramMessage) else message
            try:
                async for chunk in client.stream_media(raw, offset=offset):
                    yield chunk
            except Exception as exc:
                _raise_timeout_for_flood_wait(exc)
                raise

        return _iterate()


def _load_pyrogram_client():
    global PyrogramClient
    if PyrogramClient is _PYROGRAM_UNLOADED:
        try:
            from pyrogram import Client
        except ImportError:
            PyrogramClient = None
        else:
            PyrogramClient = Client
    if PyrogramClient is None:
        raise RuntimeError("Pyrogram download backend is not installed; install pyrogram and tgcrypto")
    return PyrogramClient


class TelegramAdapter:
    """App-owned adapter preserving the previous client surface."""

    def __init__(self, client, download_backend=None):
        self.client = client
        self.download_backend = download_backend

    async def start(self):
        await self.client.start()

    async def stop(self):
        await self.client.disconnect()
        if self.download_backend is not None:
            await self.download_backend.stop()

    async def get_me(self):
        return await self.client.get_me()

    def get_dialogs(self):
        async def _iterate():
            dialog_iter = self.client.iter_dialogs() if hasattr(self.client, "iter_dialogs") else None
            if dialog_iter is None or not hasattr(dialog_iter, "__aiter__"):
                dialog_iter = self.client.get_dialogs()
            async for dialog in dialog_iter:
                entity = getattr(dialog, "entity", None) or getattr(dialog, "chat", None)
                is_channel = bool(getattr(dialog, "is_channel", False)) or bool(getattr(entity, "broadcast", False))
                is_supergroup = bool(getattr(entity, "megagroup", False))
                chat_type = "channel" if is_channel else "supergroup" if is_supergroup else "private"
                yield SimpleNamespace(
                    chat=SimpleNamespace(
                        id=_dialog_chat_id(dialog, entity, is_channel or is_supergroup),
                        title=getattr(entity, "title", getattr(dialog, "name", None)),
                        username=getattr(entity, "username", None),
                        type=chat_type,
                    )
                )

        return _iterate()

    async def get_chat(self, chat_id: int):
        entity = await self.client.get_entity(chat_id)
        return SimpleNamespace(
            id=_entity_chat_id(entity, chat_id),
            title=getattr(entity, "title", None) or getattr(entity, "first_name", None),
            username=getattr(entity, "username", None),
            members_count=getattr(entity, "participants_count", None),
            participants_count=getattr(entity, "participants_count", None),
            description=getattr(entity, "about", None),
        )

    async def get_messages(self, chat_id: int, msg_id: int):
        try:
            message = await self.client.get_messages(chat_id, ids=msg_id)
        except Exception as exc:
            _raise_timeout_for_flood_wait(exc)
            raise
        return TelegramMessage(message)

    async def get_download_message(self, chat_id: int, msg_id: int):
        if self.download_backend is None:
            return await self.get_messages(chat_id, msg_id)
        return await self.download_backend.get_messages(chat_id, msg_id)

    def search_messages(self, chat_id: int, query: str, limit: int):
        async def _iterate():
            try:
                async for message in self.client.iter_messages(chat_id, search=query, limit=limit):
                    yield TelegramMessage(message)
            except Exception as exc:
                _raise_timeout_for_flood_wait(exc)
                raise

        return _iterate()

    def get_chat_history(self, chat_id: int, limit: int, offset_id: int = 0):
        async def _iterate():
            try:
                async for message in self.client.iter_messages(chat_id, limit=limit, offset_id=offset_id):
                    yield TelegramMessage(message)
            except Exception as exc:
                _raise_timeout_for_flood_wait(exc)
                raise

        return _iterate()

    def iter_messages(self, chat_id: int, **kwargs):
        async def _iterate():
            try:
                async for message in self.client.iter_messages(chat_id, **kwargs):
                    yield TelegramMessage(message)
            except Exception as exc:
                _raise_timeout_for_flood_wait(exc)
                raise

        return _iterate()

    async def download_media(self, message_or_media, file_name: str):
        if isinstance(message_or_media, DownloadTelegramMessage) and self.download_backend is not None:
            return await self.download_backend.download_media(message_or_media, file_name)
        raw = message_or_media.raw if isinstance(message_or_media, (TelegramMessage, TelegramMedia)) else message_or_media
        try:
            return await self.client.download_media(raw, file=file_name)
        except Exception as exc:
            _raise_timeout_for_flood_wait(exc)
            raise

    def stream_media(self, message, offset: int = 0):
        if isinstance(message, DownloadTelegramMessage) and self.download_backend is not None:
            return self.download_backend.stream_media(message, offset=offset)
        raw = message.raw if isinstance(message, TelegramMessage) else message
        byte_offset = offset * ONE_MIB

        async def _iterate():
            try:
                async for chunk in self.client.iter_download(raw, offset=byte_offset, chunk_size=ONE_MIB):
                    yield chunk
            except Exception as exc:
                _raise_timeout_for_flood_wait(exc)
                raise

        return _iterate()


async def connect_client() -> TelegramAdapter:
    global _client
    if TelegramClient is None:
        raise RuntimeError("Telethon is not installed")
    raw_client = TelegramClient(_session_path(), settings.API_ID, settings.API_HASH)
    _client = TelegramAdapter(raw_client, PyrogramDownloadBackend())
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


def get_client() -> TelegramAdapter:
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
    date = getattr(message, "date", None)
    text = _message_text(message, "text") or _message_web_page_text(message)
    caption = _message_text(message, "caption")
    body_parts = [part for part in (text, caption) if part]
    if media_info is None and not body_parts:
        return None
    item = {
        "message_id": message.id,
        "topic_id": _message_topic_id(message),
        "telegram_url": _message_telegram_url(chat_id, message),
        "sender_name": _message_sender_name(message),
        "date": date.isoformat() if date else None,
        "filename": media_info["filename"] if media_info else None,
        "file_size": media_info["size"] if media_info else None,
        "mime_type": media_info["mime_type"] if media_info else None,
        "downloadable": media_info is not None,
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


def _clean_message_text(value) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _string_attr(obj, attr: str) -> str | None:
    value = getattr(obj, attr, None)
    return value if isinstance(value, str) else None


def _int_attr(obj, attr: str) -> int | None:
    value = getattr(obj, attr, None)
    return value if isinstance(value, int) else None


def _raw_media_has_file_metadata(raw_media) -> bool:
    return any(getattr(raw_media, attr, None) is not None for attr in ("file_name", "file_size", "mime_type"))


def _dialog_chat_id(dialog, entity, is_channel_like: bool):
    raw_id = _first_int_attr(entity, "id")
    if raw_id is None:
        raw_id = _first_int_attr(dialog, "id")
    if raw_id is None:
        raw_id = _first_peer_channel_id(dialog)
    if raw_id is None:
        return getattr(entity, "id", getattr(dialog, "id", None))
    return _to_telegram_peer_id(raw_id) if is_channel_like else raw_id


def _entity_chat_id(entity, requested_chat_id: int) -> int:
    raw_id = _first_int_attr(entity, "id")
    if raw_id is None:
        return requested_chat_id
    if _is_channel_like_entity(entity) or _is_telegram_peer_id(requested_chat_id):
        return _to_telegram_peer_id(raw_id)
    return raw_id


def _is_channel_like_entity(entity) -> bool:
    return any(bool(getattr(entity, attr, False)) for attr in ("broadcast", "megagroup", "gigagroup"))


def _is_telegram_peer_id(chat_id: int) -> bool:
    return chat_id < 0 and str(abs(chat_id)).startswith("100")


def _first_int_attr(obj, attr: str) -> int | None:
    if obj is None:
        return None
    value = getattr(obj, attr, None)
    return value if isinstance(value, int) else None


def _first_peer_channel_id(dialog) -> int | None:
    for attr in ("peer_id", "peer"):
        peer = getattr(dialog, attr, None)
        channel_id = _first_int_attr(peer, "channel_id")
        if channel_id is not None:
            return channel_id
    return None


def _to_telegram_peer_id(raw_id: int) -> int:
    if raw_id < 0:
        return raw_id
    return int(f"-100{raw_id}")


def _raise_timeout_for_flood_wait(exc: Exception) -> None:
    seconds = getattr(exc, "seconds", None)
    if seconds is not None or "FloodWait" in exc.__class__.__name__:
        detail = f"Telegram flood wait: retry after {seconds} seconds" if seconds is not None else "Telegram flood wait: retry later"
        raise TimeoutError(detail) from exc


def _message_text(message, attr: str) -> str | None:
    value = getattr(message, attr, None)
    text = _clean_message_text(value)
    if text:
        return text
    for formatted_attr in ("markdown", "html"):
        formatted = getattr(value, formatted_attr, None)
        text = _clean_message_text(formatted)
        if text:
            return text
    return None


def _message_web_page_text(message) -> str | None:
    web_page = getattr(message, "web_page", None)
    if web_page is None:
        return None
    parts = []
    for attr in ("title", "description", "site_name", "url"):
        text = _clean_message_text(getattr(web_page, attr, None))
        if text:
            parts.append(text)
    return "\n".join(parts) if parts else None


def _message_topic_id(message) -> int | None:
    """Return the forum topic/thread id for a Telegram message when present."""
    if message is None:
        return None
    for attr in ("reply_to_top_message_id", "reply_to_message_id", "message_thread_id", "topic_id"):
        value = getattr(message, attr, None)
        if isinstance(value, int):
            return value
    reply = getattr(message, "reply_to_message", None)
    if reply is not None:
        value = getattr(reply, "id", None)
        if isinstance(value, int):
            return value
    return None


def _message_sender_name(message) -> str | None:
    """Return the most useful display name for the message sender."""
    sender = getattr(message, "from_user", None) or getattr(message, "sender_chat", None)
    if sender is None:
        return None
    title = _string_attr(sender, "title")
    if title:
        return title
    first_name = _string_attr(sender, "first_name")
    last_name = _string_attr(sender, "last_name")
    full_name = " ".join(part for part in (first_name, last_name) if part)
    if full_name:
        return full_name
    username = _string_attr(sender, "username")
    return f"@{username}" if username else None


def _message_telegram_url(chat_id: int, message) -> str:
    """Return a t.me URL for public and private channel messages."""
    chat = getattr(message, "chat", None)
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message.id}"
    internal_id = str(abs(chat_id))
    if internal_id.startswith("100"):
        internal_id = internal_id[3:]
    return f"https://t.me/c/{internal_id}/{message.id}"


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
    after: int | None = None,
    around: int | None = None,
    limit: int = 20,
    topic_id: int | None = None,
) -> dict:
    """Return channel messages with bidirectional cursor pagination."""
    client = get_client()
    messages: list[dict] = []
    raw_seen = 0
    last_seen_id: int | None = None
    has_newer = False
    newer_cursor: int | None = None
    has_older = False
    older_cursor: int | None = None

    async with _channel_messages_semaphore:
        if around is not None:
            # Fetch the specific found message
            found = await client.get_messages(chat_id, around)
            topic_id = topic_id if topic_id is not None else _message_topic_id(found)
            item = _message_to_channel_item(chat_id, found)
            found_item = item if item else None

            newer_items: list[dict] = []
            older_items: list[dict] = []

            # Fetch newer messages (ID > around, newest-first)
            current_limit = limit + 1 if topic_id is not None else limit
            iter_kwargs = {"reply_to": topic_id} if topic_id is not None else {}
            async for message in client.iter_messages(chat_id, limit=current_limit, min_id=around, **iter_kwargs):
                if topic_id is not None and _message_topic_id(message) != topic_id:
                    continue
                item = _message_to_channel_item(chat_id, message)
                if item:
                    newer_items.append(item)
                if len(newer_items) > limit:
                    break

            has_newer = len(newer_items) > limit if topic_id is not None else len(newer_items) >= limit
            newer_items = newer_items[:limit]
            newer_cursor = newer_items[0]["message_id"] if has_newer and newer_items else None

            # Fetch older messages (ID < around, newest-first)
            older_limit = limit + 1
            iter_kwargs = {"reply_to": topic_id} if topic_id is not None else {}
            async for message in client.iter_messages(chat_id, limit=older_limit, max_id=around, **iter_kwargs):
                raw_seen += 1
                last_seen_id = message.id
                if topic_id is not None and _message_topic_id(message) != topic_id:
                    continue
                item = _message_to_channel_item(chat_id, message)
                if item:
                    older_items.append(item)
                if len(older_items) > limit:
                    break

            has_older = len(older_items) > limit or raw_seen >= older_limit
            older_cursor = older_items[-1]["message_id"] if has_older and older_items else None

            # Build response: [newest_newer ... oldest_newer, found, newest_older ... oldest_older]
            messages = newer_items + ([found_item] if found_item else []) + older_items

        elif after is not None:
            # Fetch messages newer than `after` (newest-first)
            current_limit = limit + 1
            iter_kwargs = {"reply_to": topic_id} if topic_id is not None else {}
            async for message in client.iter_messages(chat_id, limit=current_limit, min_id=after, **iter_kwargs):
                if topic_id is not None and _message_topic_id(message) != topic_id:
                    continue
                item = _message_to_channel_item(chat_id, message)
                if item:
                    messages.append(item)
                if len(messages) > limit:
                    break

            has_older = bool(messages)
            older_cursor = messages[-1]["message_id"] if has_older and messages else None
            has_newer = len(messages) > limit if messages else False
            messages = messages[:limit]
            newer_cursor = messages[0]["message_id"] if has_newer and messages else None

        else:
            # `before` or initial channel load (newest-first)
            offset_id = before or 0
            history_limit = limit + 1
            if topic_id is not None:
                source = client.iter_messages(chat_id, limit=history_limit, offset_id=offset_id, reply_to=topic_id)
            else:
                source = client.get_chat_history(chat_id, limit=history_limit, offset_id=offset_id)
            async for message in source:
                raw_seen += 1
                last_seen_id = message.id
                if topic_id is not None and _message_topic_id(message) != topic_id:
                    continue
                item = _message_to_channel_item(chat_id, message)
                if item:
                    messages.append(item)
                if len(messages) > limit:
                    break

            page = messages[:limit]
            if page:
                has_older = len(messages) > limit or raw_seen >= history_limit
                older_cursor = page[-1]["message_id"] if has_older else None
                has_newer = before is not None
                newer_cursor = page[0]["message_id"] if has_newer else None
            else:
                has_older = False
                older_cursor = None
                has_newer = False
                newer_cursor = None
            messages = page

    return {
        "messages": messages,
        "has_older": has_older,
        "older_cursor": older_cursor,
        "has_newer": has_newer,
        "newer_cursor": newer_cursor,
        "topic_id": topic_id,
    }
