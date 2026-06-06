import os
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.telegram_client as tc_mod


@pytest.fixture(autouse=True)
def _reset_client():
    old = tc_mod._client
    tc_mod._client = None
    yield
    tc_mod._client = old


class TestGetClient:
    def test_before_connect_raises(self):
        with pytest.raises(RuntimeError, match="not initialized"):
            tc_mod.get_client()

    def test_after_setting_client(self):
        mock_client = MagicMock()
        tc_mod._client = mock_client
        assert tc_mod.get_client() is mock_client


class TestSessionPath:
    def test_joins_dir_and_name(self, test_settings):
        result = tc_mod._session_path()
        assert result == os.path.join(test_settings.SESSION_DIR, test_settings.SESSION_NAME)


class TestConnectClient:
    @patch("app.telegram_client.Client")
    async def test_connect(self, MockClient, test_settings):
        mock_instance = AsyncMock()
        mock_instance.get_me = AsyncMock(return_value=MagicMock(first_name="Test", username="testbot"))

        async def fake_dialogs():
            yield MagicMock()
            yield MagicMock()

        mock_instance.get_dialogs = fake_dialogs
        MockClient.return_value = mock_instance

        result = await tc_mod.connect_client()

        assert result is mock_instance
        mock_instance.start.assert_called_once()
        mock_instance.get_me.assert_called_once()
        assert tc_mod._client is mock_instance


class TestDisconnectClient:
    async def test_disconnect(self):
        mock_client = AsyncMock()
        tc_mod._client = mock_client
        await tc_mod.disconnect_client()
        mock_client.stop.assert_called_once()
        assert tc_mod._client is None

    async def test_disconnect_when_none(self):
        tc_mod._client = None
        await tc_mod.disconnect_client()  # Should not raise
        assert tc_mod._client is None


def _message(msg_id: int, media=None, text: str | None = None, caption: str | None = None):
    msg = MagicMock()
    msg.id = msg_id
    msg.date = datetime(2025, 1, 1, 12, msg_id % 60, tzinfo=timezone.utc)
    msg.media_group_id = None
    msg.document = media
    msg.video = None
    msg.audio = None
    msg.photo = None
    msg.text = text
    msg.caption = caption
    return msg


def _media(name: str, size: int = 1024, mime: str = "video/x-matroska"):
    media = MagicMock()
    media.file_name = name
    media.file_size = size
    media.mime_type = mime
    media.thumbs = []
    return media


async def _chat_history(messages):
    for message in messages:
        yield message


class TestGetChannelInfo:
    async def test_returns_channel_metadata(self):
        chat = MagicMock(id=-1001234, title="Series", username="series", members_count=42, description="HD")
        client = AsyncMock()
        client.get_chat = AsyncMock(return_value=chat)
        tc_mod._client = client

        result = await tc_mod.get_channel_info(-1001234)

        assert result == {
            "id": -1001234,
            "title": "Series",
            "username": "series",
            "participants_count": 42,
            "description": "HD",
        }

    async def test_raises_runtime_error_when_client_missing(self):
        tc_mod._client = None

        with pytest.raises(RuntimeError, match="not initialized"):
            await tc_mod.get_channel_info(-1001234)


class TestGetMessageThumbnail:
    async def test_downloads_thumbnail_object_not_full_media(self, tmp_path):
        media = _media("video.mkv")
        thumb = MagicMock(file_id="thumb-file")
        media.thumbs = [thumb]
        message = _message(77, media)
        thumb_path = tmp_path / "thumb.jpg"
        thumb_path.write_bytes(b"thumb")
        client = AsyncMock()
        client.get_messages = AsyncMock(return_value=message)
        client.download_media = AsyncMock(return_value=str(thumb_path))
        tc_mod._client = client

        result = await tc_mod.get_message_thumbnail(-1001234, 77, str(tmp_path))

        assert result == str(thumb_path)
        client.download_media.assert_awaited_once()
        assert client.download_media.await_args.args[0] is thumb


class TestGetChannelMessages:
    async def test_message_items_include_caption_text_and_thumbnail_url(self):
        media = _media("captioned.mkv", 100)
        media.thumbs = [MagicMock(file_id="thumb-file")]
        client = AsyncMock()
        client.get_chat_history = lambda chat_id, limit, offset_id=0: _chat_history([
            _message(42, media, text="message text", caption="release caption"),
        ])
        tc_mod._client = client

        result = await tc_mod.get_channel_messages(-1001234, limit=20)

        assert result["messages"][0] == {
            "message_id": 42,
            "date": "2025-01-01T12:42:00+00:00",
            "filename": "captioned.mkv",
            "file_size": 100,
            "mime_type": "video/x-matroska",
            "media_group_id": None,
            "text": "message text",
            "caption": "release caption",
            "body": "message text\n\nrelease caption",
            "thumbnail_url": "/api/v2/channels/-1001234/messages/42/thumbnail",
        }

    async def test_around_message_loads_found_message_before_older_history(self):
        client = AsyncMock()
        found = _message(50, _media("found.mkv", 100), caption="mismatch found")
        client.get_messages = AsyncMock(return_value=found)
        history_calls = []

        def get_chat_history(chat_id, limit, offset_id=0):
            history_calls.append((chat_id, limit, offset_id))
            return _chat_history([
                _message(49, _media("older-a.mkv", 200)),
                _message(48, _media("older-b.mkv", 300)),
            ])

        client.get_chat_history = get_chat_history
        tc_mod._client = client

        result = await tc_mod.get_channel_messages(-1001234, around=50, limit=3)

        assert [message["message_id"] for message in result["messages"]] == [50, 49, 48]
        assert result["messages"][0]["caption"] == "mismatch found"
        client.get_messages.assert_awaited_once_with(-1001234, 50)
        assert history_calls == [(-1001234, 3, 50)]

    async def test_returns_paginated_downloadable_messages(self):
        client = AsyncMock()
        history_calls = []

        def get_chat_history(chat_id, limit, offset_id=0):
            history_calls.append((chat_id, limit, offset_id))
            return _chat_history([
                _message(30, _media("a.mkv", 100)),
                _message(29, None),
                _message(28, _media("b.mkv", 200)),
            ])

        client.get_chat_history = get_chat_history
        tc_mod._client = client

        result = await tc_mod.get_channel_messages(-1001234, before=31, limit=2)

        assert result["messages"] == [
            {
                "message_id": 30,
                "date": "2025-01-01T12:30:00+00:00",
                "filename": "a.mkv",
                "file_size": 100,
                "mime_type": "video/x-matroska",
                "media_group_id": None,
                "text": None,
                "caption": None,
                "body": None,
                "thumbnail_url": None,
            },
            {
                "message_id": 28,
                "date": "2025-01-01T12:28:00+00:00",
                "filename": "b.mkv",
                "file_size": 200,
                "mime_type": "video/x-matroska",
                "media_group_id": None,
                "text": None,
                "caption": None,
                "body": None,
                "thumbnail_url": None,
            },
        ]
        assert result["has_more"] is True
        assert result["next_cursor"] == 28
        assert history_calls == [(-1001234, 3, 31)]

    async def test_returns_no_cursor_when_less_than_limit(self):
        client = AsyncMock()
        history_calls = []

        def get_chat_history(chat_id, limit, offset_id=0):
            history_calls.append((chat_id, limit, offset_id))
            return _chat_history([
                _message(10, _media("single.mkv", 100)),
            ])

        client.get_chat_history = get_chat_history
        tc_mod._client = client

        result = await tc_mod.get_channel_messages(-1001234, limit=20)

        assert len(result["messages"]) == 1
        assert result["has_more"] is False
        assert result["next_cursor"] is None
        assert history_calls == [(-1001234, 21, 0)]

    async def test_semaphore_limits_two_concurrent_calls(self):
        started = 0
        release = asyncio.Event()
        entered_third = asyncio.Event()

        async def slow_iter(_messages):
            nonlocal started
            started += 1
            if started == 3:
                entered_third.set()
            await release.wait()
            yield _message(100 + started, _media(f"{started}.mkv"))

        client = AsyncMock()
        client.get_chat_history = lambda chat_id, limit, offset_id=0: slow_iter([])
        tc_mod._client = client

        tasks = [asyncio.create_task(tc_mod.get_channel_messages(-1001234)) for _ in range(3)]
        await asyncio.sleep(0.05)

        assert started == 2
        assert not entered_third.is_set()

        release.set()
        await asyncio.gather(*tasks)
        assert started == 3
