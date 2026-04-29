import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import get_settings, Settings


# ---------------------------------------------------------------------------
# Settings fixture — isolated from .env file
# ---------------------------------------------------------------------------

class _TestSettings(Settings):
    model_config = {"env_file": None, "extra": "ignore"}


@pytest.fixture
def test_settings(tmp_path, monkeypatch):
    """Provide a Settings instance pointing at tmp_path directories."""
    monkeypatch.setenv("API_ID", "12345")
    monkeypatch.setenv("API_HASH", "testhash")
    monkeypatch.setenv("TORZNAB_APIKEY", "testapikey")
    monkeypatch.setenv("BASE_URL", "http://localhost:9117")
    monkeypatch.setenv("DOWNLOAD_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("CHANNELS_FILE", str(tmp_path / "channels.json"))
    monkeypatch.setenv("SESSION_DIR", str(tmp_path))
    monkeypatch.setenv("SESSION_NAME", "test_session")

    get_settings.cache_clear()
    s = _TestSettings()
    monkeypatch.setattr("app.config.get_settings", lambda: s)
    # Patch settings proxy to use our test settings
    for mod in (
        "app.download", "app.stream", "app.channels",
        "app.torznab.router", "app.torznab.search", "app.torznab.caps",
        "app.transmission.state", "app.transmission.router",
        "app.transmission.handlers", "app.transmission.downloader",
        "app.telegram_client",
    ):
        try:
            monkeypatch.setattr(f"{mod}.settings", s)
        except AttributeError:
            pass
    yield s
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Telegram client mock
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_telegram_client(monkeypatch):
    """AsyncMock standing in for pyrogram.Client."""
    client = AsyncMock()
    client.get_me = AsyncMock(return_value=MagicMock(first_name="Test", username="testbot"))
    client.get_messages = AsyncMock()
    client.get_chat = AsyncMock()
    client.search_messages = AsyncMock()
    client.stream_media = AsyncMock()
    client.download_media = AsyncMock()
    client.start = AsyncMock()
    client.stop = AsyncMock()

    monkeypatch.setattr("app.telegram_client._client", client)
    monkeypatch.setattr("app.telegram_client.get_client", lambda: client)
    # Also patch modules that import get_client directly
    for mod in ("app.download", "app.stream", "app.torznab.search", "app.transmission.downloader"):
        try:
            monkeypatch.setattr(f"{mod}.get_client", lambda: client)
        except AttributeError:
            pass
    return client


# ---------------------------------------------------------------------------
# Mock message factory
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_message():
    """Factory to create mock Telegram messages."""
    def _make(
        msg_id=1,
        file_name="test.mkv",
        file_size=1048576,
        mime_type="video/x-matroska",
        text="",
        date=None,
        has_document=True,
        media_type="document",  # "document", "video", or None
    ):
        from datetime import datetime, timezone
        msg = MagicMock()
        msg.id = msg_id
        msg.text = text
        msg.caption = None
        msg.date = date or datetime(2025, 1, 1, tzinfo=timezone.utc)
        msg.empty = False
        msg.document = None
        msg.video = None
        if has_document:
            media = MagicMock()
            media.file_name = file_name
            media.file_size = file_size
            media.mime_type = mime_type
            if media_type == "video":
                msg.video = media
            else:
                msg.document = media
        return msg
    return _make


# ---------------------------------------------------------------------------
# Channel fixtures
# ---------------------------------------------------------------------------

SAMPLE_CHANNELS = [
    {"chat_id": "-1001234", "category_id": 1000, "name": "TestChannel1", "username": "testchan1"},
    {"chat_id": "-1005678", "category_id": 1001, "name": "TestChannel2", "username": None},
]


@pytest.fixture
def sample_channels():
    return list(SAMPLE_CHANNELS)


@pytest.fixture
def populated_channels(monkeypatch, sample_channels):
    """Load sample channels into the channels module's internal state."""
    import app.channels as ch_mod
    old_channels = ch_mod._channels[:]
    old_by_cat = dict(ch_mod._by_category)
    old_by_chat = dict(ch_mod._by_chat)

    ch_mod._channels[:] = sample_channels
    ch_mod._by_category.clear()
    ch_mod._by_chat.clear()
    ch_mod._by_category.update({c["category_id"]: c for c in sample_channels})
    ch_mod._by_chat.update({c["chat_id"]: c for c in sample_channels})

    yield sample_channels

    ch_mod._channels[:] = old_channels
    ch_mod._by_category.clear()
    ch_mod._by_category.update(old_by_cat)
    ch_mod._by_chat.clear()
    ch_mod._by_chat.update(old_by_chat)


# ---------------------------------------------------------------------------
# Transmission state fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_downloads(monkeypatch):
    """Reset transmission download state."""
    import app.transmission.state as state_mod
    old_downloads = dict(state_mod._downloads)
    old_next_id = state_mod._next_id

    state_mod._downloads.clear()
    state_mod._next_id = 1

    yield state_mod._downloads

    state_mod._downloads.clear()
    state_mod._downloads.update(old_downloads)
    state_mod._next_id = old_next_id


# ---------------------------------------------------------------------------
# FastAPI test app (no lifespan, no real Telegram)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_app(test_settings, mock_telegram_client, populated_channels, clean_downloads):
    """FastAPI app for integration testing with all routers included."""
    from app.torznab.router import router as torznab_router
    from app.download import router as download_router
    from app.stream import router as stream_router
    from app.transmission.router import router as transmission_router

    app = FastAPI()
    app.include_router(torznab_router)
    app.include_router(download_router)
    app.include_router(stream_router)
    app.include_router(transmission_router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "Telegram Torznab"}

    return app


@pytest.fixture
async def async_client(test_app):
    """httpx AsyncClient for testing FastAPI endpoints."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
