import os
import logging
from telethon import TelegramClient
from app.config import settings

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None


def _session_path() -> str:
    return os.path.join(settings.SESSION_DIR, settings.SESSION_NAME)


async def connect_client() -> TelegramClient:
    global _client
    _client = TelegramClient(_session_path(), settings.API_ID, settings.API_HASH)
    await _client.connect()
    if not await _client.is_user_authorized():
        raise RuntimeError(
            "Telegram session not authorized. "
            "Run: docker compose --profile auth run --rm torznab-auth"
        )
    me = await _client.get_me()
    logger.info("Telegram connected as %s (@%s)", me.first_name, me.username)
    return _client


async def disconnect_client():
    global _client
    if _client:
        await _client.disconnect()
        _client = None


def get_client() -> TelegramClient:
    if _client is None:
        raise RuntimeError("Telegram client not initialized")
    return _client
