import os
import logging
from pyrogram import Client
from app.config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None


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
