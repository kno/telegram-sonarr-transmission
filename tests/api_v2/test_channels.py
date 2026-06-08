from unittest.mock import AsyncMock, MagicMock
import importlib
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

APIKEY = "testapikey"


@pytest.fixture
def patch_channel_helpers(monkeypatch):
    info = {
        "id": -1001234,
        "title": "TestChannel1",
        "username": "testchan1",
        "participants_count": 1200,
        "description": "Series HD",
    }
    messages = {
        "messages": [
            {
                "message_id": 251258,
                "topic_id": 205000,
                "telegram_url": "https://t.me/c/2589145533/251258",
                "sender_name": "Uploader",
                "date": "2025-06-01T14:30:00+00:00",
                "filename": "Show.S02E03.720p.mkv",
                "file_size": 1073741824,
                "mime_type": "video/x-matroska",
                "downloadable": True,
                "media_group_id": None,
                "text": None,
                "caption": "Release caption",
                "thumbnail_url": "/api/v2/channels/-1001234/messages/251258/thumbnail",
            }
        ],
        "has_older": False,
        "older_cursor": None,
        "has_newer": False,
        "newer_cursor": None,
        "topic_id": 205000,
    }
    get_info = AsyncMock(return_value=info)
    get_messages = AsyncMock(return_value=messages)
    router_mod = importlib.import_module("app.api_v2.router")
    monkeypatch.setattr(router_mod, "get_channel_info", get_info)
    monkeypatch.setattr(router_mod, "get_channel_messages", get_messages)
    return get_info, get_messages


class TestChannelInfoEndpoint:
    async def test_returns_metadata_for_known_channel(self, async_client, patch_channel_helpers):
        resp = await async_client.get(f"/api/v2/channels/-1001234?apikey={APIKEY}")

        assert resp.status_code == 200
        assert resp.json() == {
            "id": -1001234,
            "title": "TestChannel1",
            "username": "testchan1",
            "participants_count": 1200,
            "description": "Series HD",
        }

    async def test_rejects_invalid_api_key(self, async_client):
        resp = await async_client.get("/api/v2/channels/-1001234?apikey=bad")

        assert resp.status_code == 401

    async def test_unknown_channel_returns_404(self, async_client, patch_channel_helpers):
        resp = await async_client.get(f"/api/v2/channels/-1009999?apikey={APIKEY}")

        assert resp.status_code == 404
        assert "Unknown channel" in resp.json()["detail"]


class TestChannelMessagesEndpoint:
    async def test_returns_messages_and_channel_metadata(self, async_client, patch_channel_helpers):
        get_info, get_messages = patch_channel_helpers

        resp = await async_client.get(f"/api/v2/channels/-1001234/messages?apikey={APIKEY}&limit=20")

        assert resp.status_code == 200
        data = resp.json()
        assert data["channel"] == {
            "id": -1001234,
            "title": "TestChannel1",
            "username": "testchan1",
            "participants_count": 1200,
            "description": "Series HD",
        }
        assert data["messages"][0]["message_id"] == 251258
        assert data["messages"][0]["caption"] == "Release caption"
        assert data["messages"][0]["thumbnail_url"] == "/api/v2/channels/-1001234/messages/251258/thumbnail"
        assert data["has_older"] is False
        assert data["older_cursor"] is None
        assert data["has_newer"] is False
        assert data["newer_cursor"] is None
        get_info.assert_awaited_once_with(-1001234)
        get_messages.assert_awaited_once_with(-1001234, before=None, after=None, around=None, limit=20, topic_id=None)

    async def test_passes_cursor_to_telegram_helper(self, async_client, patch_channel_helpers):
        _, get_messages = patch_channel_helpers

        resp = await async_client.get(
            f"/api/v2/channels/-1001234/messages?apikey={APIKEY}&before=251240&limit=10"
        )

        assert resp.status_code == 200
        get_messages.assert_awaited_once_with(-1001234, before=251240, after=None, around=None, limit=10, topic_id=None)

    async def test_can_skip_channel_metadata_for_paginated_messages(self, async_client, patch_channel_helpers):
        get_info, get_messages = patch_channel_helpers

        resp = await async_client.get(
            f"/api/v2/channels/-1001234/messages?apikey={APIKEY}&before=251240&limit=10&include_channel=false"
        )

        assert resp.status_code == 200
        assert resp.json()["channel"] == {"id": -1001234, "title": "TestChannel1"}
        get_info.assert_not_awaited()
        get_messages.assert_awaited_once_with(-1001234, before=251240, after=None, around=None, limit=10, topic_id=None)

    async def test_passes_around_message_to_telegram_helper(self, async_client, patch_channel_helpers):
        _, get_messages = patch_channel_helpers

        resp = await async_client.get(
            f"/api/v2/channels/-1001234/messages?apikey={APIKEY}&around=251258&limit=20"
        )

        assert resp.status_code == 200
        get_messages.assert_awaited_once_with(-1001234, before=None, after=None, around=251258, limit=20, topic_id=None)

    async def test_passes_topic_to_telegram_helper(self, async_client, patch_channel_helpers):
        _, get_messages = patch_channel_helpers

        resp = await async_client.get(
            f"/api/v2/channels/-1001234/messages?apikey={APIKEY}&before=251240&limit=10&topic_id=205000"
        )

        assert resp.status_code == 200
        get_messages.assert_awaited_once_with(-1001234, before=251240, after=None, around=None, limit=10, topic_id=205000)

    async def test_limit_above_max_returns_422(self, async_client):
        resp = await async_client.get(f"/api/v2/channels/-1001234/messages?apikey={APIKEY}&limit=100")

        assert resp.status_code == 422

    async def test_unknown_channel_returns_404(self, async_client, patch_channel_helpers):
        resp = await async_client.get(f"/api/v2/channels/-1009999/messages?apikey={APIKEY}")

        assert resp.status_code == 404

    async def test_flood_wait_returns_429(self, async_client, patch_channel_helpers):
        _, get_messages = patch_channel_helpers
        get_messages.side_effect = TimeoutError("Flood wait: retry later")

        resp = await async_client.get(f"/api/v2/channels/-1001234/messages?apikey={APIKEY}")

        assert resp.status_code == 429
        assert "retry" in resp.json()["detail"].lower()

    async def test_disconnected_client_returns_502(self, async_client, patch_channel_helpers):
        _, get_messages = patch_channel_helpers
        get_messages.side_effect = RuntimeError("Telegram client not initialized")

        resp = await async_client.get(f"/api/v2/channels/-1001234/messages?apikey={APIKEY}")

        assert resp.status_code == 502
        assert "Telegram" in resp.json()["detail"]


class TestChannelThumbnailEndpoint:
    async def test_returns_thumbnail_file_for_known_channel(self, async_client, patch_channel_helpers, monkeypatch, tmp_path):
        thumb_path = tmp_path / "thumb.jpg"
        thumb_path.write_bytes(b"thumb")
        router_mod = importlib.import_module("app.api_v2.router")
        get_thumb = AsyncMock(return_value=str(thumb_path))
        monkeypatch.setattr(router_mod, "get_message_thumbnail", get_thumb)

        resp = await async_client.get(
            f"/api/v2/channels/-1001234/messages/251258/thumbnail?apikey={APIKEY}"
        )

        assert resp.status_code == 200
        assert resp.content == b"thumb"
        get_thumb.assert_awaited_once()
        assert get_thumb.await_args.args[:2] == (-1001234, 251258)


class TestApiV2SearchEndpoint:
    async def test_search_returns_stable_fetchable_ids_and_download_url(
        self, async_client, mock_telegram_client, mock_message, test_settings
    ):
        matched_text = mock_message(
            msg_id=251257,
            has_document=False,
            text="The Last Spark of Hope",
            date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        paired_media = mock_message(
            msg_id=251258,
            file_name="The.Last.Spark.of.Hope.S01E01.mkv",
            file_size=1073741824,
            mime_type="video/x-matroska",
            date=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )

        def search_messages(chat_id, query, limit):
            async def gen():
                if chat_id == -1001234:
                    yield matched_text

            return gen()

        mock_telegram_client.search_messages = MagicMock(side_effect=search_messages)
        mock_telegram_client.get_messages = AsyncMock(return_value=paired_media)

        resp = await async_client.get(
            f"/api/v2/search?apikey={test_settings.TORZNAB_APIKEY}&q=last+spark&limit=10"
        )

        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["guid"] == "-1001234:251258"
        assert item["chatId"] == "-1001234"
        assert item["msgId"] == 251258
        parsed = urlparse(item["downloadUrl"])
        assert parsed.path == "/api/download"
        assert parse_qs(parsed.query)["id"] == ["-1001234:251258"]
        assert parse_qs(parsed.query)["apikey"] == [test_settings.TORZNAB_APIKEY]

    async def test_search_drops_text_match_when_paired_message_is_not_downloadable(
        self, async_client, mock_telegram_client, mock_message, test_settings
    ):
        matched_text = mock_message(msg_id=10, has_document=False, text="Text only result")
        next_text = mock_message(msg_id=11, has_document=False, text="Still no media")

        def search_messages(chat_id, query, limit):
            async def gen():
                yield matched_text

            return gen()

        mock_telegram_client.search_messages = MagicMock(side_effect=search_messages)
        mock_telegram_client.get_messages = AsyncMock(return_value=next_text)

        resp = await async_client.get(
            f"/api/v2/search?apikey={test_settings.TORZNAB_APIKEY}&q=text&limit=10"
        )

        assert resp.status_code == 200
        assert resp.json()["items"] == []
