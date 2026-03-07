import json
import logging
import os
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_channels: list[dict] = []
_by_category: dict[int, dict] = {}
_by_chat: dict[str, dict] = {}


def load_channels() -> list[dict]:
    """Load channels from channels.json."""
    global _channels, _by_category, _by_chat
    path = settings.CHANNELS_FILE
    if os.path.exists(path):
        with open(path) as f:
            _channels = json.load(f)
        _rebuild_indexes()
        logger.info("Loaded %d channels from %s", len(_channels), path)
    return _channels


def save_channels(channels: list[dict]):
    """Persist channel mapping to disk."""
    global _channels
    _channels = channels
    os.makedirs(os.path.dirname(settings.CHANNELS_FILE), exist_ok=True)
    with open(settings.CHANNELS_FILE, "w") as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)
    _rebuild_indexes()


def import_user_channels(path: str) -> list[dict]:
    """Import channels from docker-crawl's user_channels.json format."""
    with open(path) as f:
        data = json.load(f)

    channels = []
    cat_id = 1000
    for ch in data.get("marked_channels", []):
        channels.append({
            "chat_id": str(ch["id"]),
            "category_id": cat_id,
            "name": ch["name"],
        })
        cat_id += 1
    for gr in data.get("marked_groups", []):
        channels.append({
            "chat_id": str(gr["id"]),
            "category_id": cat_id,
            "name": gr["name"],
        })
        cat_id += 1

    logger.info("Imported %d channels from %s", len(channels), path)
    return channels


async def auto_discover_channels(client) -> list[dict]:
    """Discover channels via Telegram get_dialogs()."""
    from pyrogram.enums import ChatType

    channels = []
    cat_id = 1000
    async for dialog in client.get_dialogs():
        chat = dialog.chat
        if chat.type in (ChatType.CHANNEL, ChatType.SUPERGROUP):
            channels.append({
                "chat_id": str(chat.id),
                "category_id": cat_id,
                "name": chat.title or "Unknown",
                "username": chat.username,
            })
            cat_id += 1
    logger.info("Discovered %d channels via Telegram", len(channels))
    return channels


async def init_channels():
    """Initialize channel mapping on startup. Auto-discovers if no config exists."""
    loaded = load_channels()
    if loaded:
        return

    # Try importing from user_channels.json
    if settings.USER_CHANNELS_FILE and os.path.exists(settings.USER_CHANNELS_FILE):
        channels = import_user_channels(settings.USER_CHANNELS_FILE)
        save_channels(channels)
        return

    # Auto-discover all channels from Telegram
    from app.telegram_client import get_client
    logger.info("No channels.json found. Auto-discovering channels from Telegram...")
    client = get_client()
    channels = await auto_discover_channels(client)
    if channels:
        save_channels(channels)
        logger.info("Saved %d discovered channels to %s", len(channels), settings.CHANNELS_FILE)
    else:
        logger.warning("No channels found in Telegram account.")


def _rebuild_indexes():
    global _by_category, _by_chat
    _by_category = {ch["category_id"]: ch for ch in _channels}
    _by_chat = {ch["chat_id"]: ch for ch in _channels}


def get_all_channels() -> list[dict]:
    return _channels


def get_channel_by_category(cat_id: int) -> Optional[dict]:
    return _by_category.get(cat_id)


def get_category_by_chat(chat_id: str) -> Optional[dict]:
    return _by_chat.get(chat_id)
