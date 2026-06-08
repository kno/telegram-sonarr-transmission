import os
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
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
    def test_uses_telethon_specific_session_name(self, test_settings):
        result = tc_mod._session_path()
        assert result == os.path.join(test_settings.SESSION_DIR, f"{test_settings.SESSION_NAME}_telethon")

    def test_preserves_explicit_telethon_session_name(self, test_settings, monkeypatch):
        monkeypatch.setattr(test_settings, "SESSION_NAME", "custom_telethon")

        assert tc_mod._session_path() == os.path.join(test_settings.SESSION_DIR, "custom_telethon")


class TestConnectClient:
    @patch("app.telegram_client.TelegramClient")
    async def test_connect(self, MockClient, test_settings):
        mock_instance = AsyncMock()
        mock_instance.get_me = AsyncMock(return_value=MagicMock(first_name="Test", username="testbot"))

        async def fake_dialogs():
            yield MagicMock()
            yield MagicMock()

        mock_instance.iter_dialogs = fake_dialogs
        MockClient.return_value = mock_instance

        result = await tc_mod.connect_client()

        assert isinstance(result, tc_mod.TelegramAdapter)
        mock_instance.start.assert_called_once()
        mock_instance.get_me.assert_called_once()
        assert tc_mod._client is result


class TestTelegramAdapter:
    async def test_get_dialogs_normalizes_channel_entity_ids_to_peer_ids(self):
        raw_client = AsyncMock()
        entity = SimpleNamespace(id=1234567890, title="Series", username="series", broadcast=True)
        dialog = SimpleNamespace(entity=entity, is_channel=True)

        async def iter_dialogs():
            yield dialog

        raw_client.iter_dialogs = iter_dialogs
        adapter = tc_mod.TelegramAdapter(raw_client)

        results = [dialog async for dialog in adapter.get_dialogs()]

        assert results[0].chat.id == -1001234567890
        assert results[0].chat.title == "Series"
        assert results[0].chat.username == "series"
        assert results[0].chat.type == "channel"

    async def test_get_dialogs_normalizes_peer_channel_id_when_entity_is_missing(self):
        raw_client = AsyncMock()
        peer_id = SimpleNamespace(channel_id=987654321)
        dialog = SimpleNamespace(id=None, peer=peer_id, peer_id=peer_id, name="Peer Channel", is_channel=True)

        async def iter_dialogs():
            yield dialog

        raw_client.iter_dialogs = iter_dialogs
        adapter = tc_mod.TelegramAdapter(raw_client)

        results = [dialog async for dialog in adapter.get_dialogs()]

        assert results[0].chat.id == -100987654321
        assert results[0].chat.title == "Peer Channel"

    async def test_get_chat_normalizes_channel_entity_id_to_peer_id(self):
        raw_client = AsyncMock()
        raw_client.get_entity = AsyncMock(return_value=SimpleNamespace(
            id=1234567890,
            title="Series",
            username="series",
            broadcast=True,
            participants_count=42,
            about="HD releases",
        ))
        adapter = tc_mod.TelegramAdapter(raw_client)

        result = await adapter.get_chat(-1001234567890)

        assert result.id == -1001234567890
        assert result.title == "Series"
        assert result.username == "series"
        assert result.members_count == 42
        assert result.description == "HD releases"

    async def test_get_chat_normalizes_peer_channel_style_id_for_supergroup(self):
        raw_client = AsyncMock()
        raw_client.get_entity = AsyncMock(return_value=SimpleNamespace(
            id=987654321,
            title="Peer Channel",
            username=None,
            megagroup=True,
            participants_count=7,
            about=None,
        ))
        adapter = tc_mod.TelegramAdapter(raw_client)

        result = await adapter.get_chat(987654321)

        assert result.id == -100987654321
        assert result.title == "Peer Channel"

    async def test_get_chat_keeps_non_channel_entity_id(self):
        raw_client = AsyncMock()
        raw_client.get_entity = AsyncMock(return_value=SimpleNamespace(
            id=12345,
            first_name="Uploader",
            username="uploader",
            participants_count=None,
            about=None,
        ))
        adapter = tc_mod.TelegramAdapter(raw_client)

        result = await adapter.get_chat(12345)

        assert result.id == 12345
        assert result.title == "Uploader"

    async def test_search_messages_wraps_telethon_messages(self):
        raw_message = MagicMock()
        raw_message.id = 10
        raw_message.message = "caption text"
        raw_message.text = "caption text"
        raw_message.date = datetime(2025, 1, 1, tzinfo=timezone.utc)
        raw_message.file = SimpleNamespace(name="release.mkv", size=2048, mime_type="video/x-matroska")
        raw_client = AsyncMock()

        async def iter_messages(entity, search=None, limit=None, offset_id=0):
            yield raw_message

        raw_client.iter_messages = iter_messages
        adapter = tc_mod.TelegramAdapter(raw_client)

        results = [message async for message in adapter.search_messages(-1001234, "release", limit=5)]

        assert len(results) == 1
        assert results[0].id == 10
        assert results[0].caption == "caption text"
        assert results[0].document.file_name == "release.mkv"
        assert results[0].document.file_size == 2048

    async def test_stream_media_uses_one_mib_byte_offsets(self):
        raw_message = MagicMock()
        raw_client = AsyncMock()
        calls = []

        async def iter_download(media, offset=0, chunk_size=None):
            calls.append((media, offset, chunk_size))
            yield b"chunk"

        raw_client.iter_download = iter_download
        adapter = tc_mod.TelegramAdapter(raw_client)

        chunks = [chunk async for chunk in adapter.stream_media(raw_message, offset=3)]

        assert chunks == [b"chunk"]
        assert calls == [(raw_message, 3 * 1024 * 1024, 1024 * 1024)]

    async def test_download_message_uses_pyrogram_backend_when_configured(self):
        raw_client = AsyncMock()
        raw_client.get_messages = AsyncMock()
        backend = AsyncMock()
        backend.get_messages = AsyncMock(return_value=MagicMock(id=42))
        adapter = tc_mod.TelegramAdapter(raw_client, backend)

        result = await adapter.get_download_message(-1001234, 42)

        assert result.id == 42
        backend.get_messages.assert_awaited_once_with(-1001234, 42)
        raw_client.get_messages.assert_not_awaited()

    async def test_search_messages_still_uses_telethon_with_download_backend(self):
        raw_message = MagicMock(id=10, message="release", text="release", file=None, media=None)
        raw_client = AsyncMock()
        backend = AsyncMock()

        async def iter_messages(entity, search=None, limit=None, offset_id=0):
            yield raw_message

        raw_client.iter_messages = iter_messages
        adapter = tc_mod.TelegramAdapter(raw_client, backend)

        results = [message async for message in adapter.search_messages(-1001234, "release", limit=5)]

        assert results[0].id == 10
        backend.get_messages.assert_not_called()

    async def test_pyrogram_download_backend_refetches_telethon_peer_id(self, test_settings, tmp_path, monkeypatch):
        session_file = tmp_path / "test_session.session"
        session_file.write_text("legacy pyrogram session")
        raw_message = MagicMock(id=42)
        calls = []

        class FakePyrogramClient:
            def __init__(self, name, api_id, api_hash, workdir):
                calls.append(("init", name, api_id, api_hash, workdir))

            async def start(self):
                calls.append(("start",))

            async def stop(self):
                calls.append(("stop",))

            async def get_messages(self, chat_id, msg_id):
                calls.append(("get_messages", chat_id, msg_id))
                return raw_message

            async def download_media(self, message, file_name=None):
                calls.append(("download_media", message, file_name))
                return file_name

            async def stream_media(self, message, offset=0):
                calls.append(("stream_media", message, offset))
                yield b"chunk"

        monkeypatch.setattr(tc_mod, "PyrogramClient", FakePyrogramClient)
        backend = tc_mod.PyrogramDownloadBackend()

        message = await backend.get_messages(-1001234567890, 42)
        downloaded = await backend.download_media(message, file_name="/tmp/video.mkv")
        chunks = [chunk async for chunk in backend.stream_media(message, offset=3)]
        await backend.stop()

        assert isinstance(message, tc_mod.DownloadTelegramMessage)
        assert message.id == 42
        assert downloaded == "/tmp/video.mkv"
        assert chunks == [b"chunk"]
        assert calls == [
            ("init", "test_session", 12345, "testhash", str(tmp_path)),
            ("start",),
            ("get_messages", -1001234567890, 42),
            ("download_media", raw_message, "/tmp/video.mkv"),
            ("stream_media", raw_message, 3),
            ("stop",),
        ]

    async def test_pyrogram_download_backend_starts_once_for_concurrent_first_requests(
        self, test_settings, tmp_path, monkeypatch
    ):
        session_file = tmp_path / "test_session.session"
        session_file.write_text("legacy pyrogram session")
        start_entered = asyncio.Event()
        release_start = asyncio.Event()
        calls = []

        class FakePyrogramClient:
            def __init__(self, name, api_id, api_hash, workdir):
                calls.append(("init", name, api_id, api_hash, workdir))

            async def start(self):
                calls.append(("start",))
                start_entered.set()
                await release_start.wait()

            async def get_messages(self, chat_id, msg_id):
                calls.append(("get_messages", chat_id, msg_id))
                return MagicMock(id=msg_id)

            async def stop(self):
                calls.append(("stop",))

        monkeypatch.setattr(tc_mod, "PyrogramClient", FakePyrogramClient)
        backend = tc_mod.PyrogramDownloadBackend()

        first = asyncio.create_task(backend.get_messages(-1001234567890, 42))
        await start_entered.wait()
        second = asyncio.create_task(backend.get_messages(-1001234567890, 43))
        await asyncio.sleep(0)

        assert calls == [("init", "test_session", 12345, "testhash", str(tmp_path)), ("start",)]

        release_start.set()
        first_message, second_message = await asyncio.gather(first, second)
        await backend.stop()

        assert first_message.id == 42
        assert second_message.id == 43
        assert calls == [
            ("init", "test_session", 12345, "testhash", str(tmp_path)),
            ("start",),
            ("get_messages", -1001234567890, 42),
            ("get_messages", -1001234567890, 43),
            ("stop",),
        ]

    async def test_pyrogram_download_backend_missing_session_has_clear_error(self, test_settings, monkeypatch):
        monkeypatch.setattr(tc_mod, "PyrogramClient", MagicMock())
        backend = tc_mod.PyrogramDownloadBackend()

        with pytest.raises(RuntimeError, match="Pyrogram download session not found"):
            await backend.get_messages(-1001234, 42)

    async def test_pyrogram_download_backend_missing_dependency_has_clear_error(self, test_settings):
        backend = tc_mod.PyrogramDownloadBackend()
        old_client = tc_mod.PyrogramClient
        tc_mod.PyrogramClient = None
        try:
            with pytest.raises(RuntimeError, match="Pyrogram download backend is not installed"):
                await backend.get_messages(-1001234, 42)
        finally:
            tc_mod.PyrogramClient = old_client

    async def test_search_messages_maps_flood_wait_to_timeout_error(self):
        class FloodWaitError(Exception):
            seconds = 17

        raw_client = AsyncMock()

        async def iter_messages(entity, search=None, limit=None, offset_id=0):
            raise FloodWaitError("wait")
            yield None

        raw_client.iter_messages = iter_messages
        adapter = tc_mod.TelegramAdapter(raw_client)

        with pytest.raises(TimeoutError, match="17"):
            [message async for message in adapter.search_messages(-1001234, "release", limit=5)]

    def test_message_does_not_wrap_webpage_preview_as_downloadable_media(self):
        webpage = SimpleNamespace(title="Release preview")
        raw_message = SimpleNamespace(
            id=20,
            message="https://example.test/release",
            text="https://example.test/release",
            date=None,
            chat=None,
            sender=None,
            media=SimpleNamespace(webpage=webpage),
            file=None,
            web_preview=webpage,
            grouped_id=None,
            reply_to_top_id=None,
            reply_to_msg_id=None,
            empty=False,
        )

        wrapped = tc_mod.TelegramMessage(raw_message)

        assert wrapped.document is None
        assert wrapped.video is None
        assert wrapped.audio is None
        assert wrapped.photo is None
        assert wrapped.web_page is webpage

    def test_message_wraps_downloadable_file_media(self):
        raw_message = SimpleNamespace(
            id=21,
            message="release",
            text="release",
            date=None,
            chat=None,
            sender=None,
            media=SimpleNamespace(thumbs=[]),
            file=SimpleNamespace(name="release.mkv", size=2048, mime_type="video/x-matroska"),
            web_preview=None,
            grouped_id=None,
            reply_to_top_id=None,
            reply_to_msg_id=None,
            empty=False,
        )

        wrapped = tc_mod.TelegramMessage(raw_message)

        assert wrapped.document.file_name == "release.mkv"
        assert wrapped.document.file_size == 2048
        assert wrapped.video is wrapped.document


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


def _message(
    msg_id: int,
    media=None,
    text: str | None = None,
    caption: str | None = None,
    topic_id: int | None = None,
    sender_name: str | None = "Uploader",
    chat_username: str | None = "series",
):
    msg = MagicMock()
    msg.id = msg_id
    msg.reply_to_top_message_id = topic_id
    msg.reply_to_message_id = None
    msg.message_thread_id = None
    msg.topic_id = None
    msg.reply_to_message = None
    msg.chat = MagicMock(username=chat_username)
    msg.from_user = MagicMock(first_name=sender_name, last_name=None, username=None) if sender_name else None
    msg.sender_chat = None
    msg.date = datetime(2025, 1, 1, 12, msg_id % 60, tzinfo=timezone.utc)
    msg.media_group_id = None
    msg.document = media
    msg.video = None
    msg.audio = None
    msg.photo = None
    msg.text = text
    msg.caption = caption
    msg.web_page = None
    return msg


def _message_with_reply_id(msg_id: int, media=None, reply_to_message_id: int | None = None):
    msg = _message(msg_id, media)
    msg.reply_to_top_message_id = None
    msg.reply_to_message_id = reply_to_message_id
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
            "topic_id": None,
            "telegram_url": "https://t.me/series/42",
            "sender_name": "Uploader",
            "date": "2025-01-01T12:42:00+00:00",
            "filename": "captioned.mkv",
            "file_size": 100,
            "mime_type": "video/x-matroska",
            "downloadable": True,
            "media_group_id": None,
            "text": "message text",
            "caption": "release caption",
            "body": "message text\n\nrelease caption",
            "thumbnail_url": "/api/v2/channels/-1001234/messages/42/thumbnail",
        }

    async def test_message_items_use_web_page_text_fallback(self):
        client = AsyncMock()
        message = _message(43, None)
        message.web_page = MagicMock(
            title="Release notes",
            description="Image preview with useful text",
            site_name=None,
            url="https://example.test/release",
        )
        client.get_chat_history = lambda chat_id, limit, offset_id=0: _chat_history([message])
        tc_mod._client = client

        result = await tc_mod.get_channel_messages(-1001234, limit=20)

        assert result["messages"][0]["text"] == "Release notes\nImage preview with useful text\nhttps://example.test/release"
        assert result["messages"][0]["body"] == "Release notes\nImage preview with useful text\nhttps://example.test/release"

    async def test_around_message_loads_newer_and_older_messages(self):
        client = AsyncMock()
        found = _message(50, _media("found.mkv", 100), caption="mismatch found")
        client.get_messages = AsyncMock(return_value=found)
        iter_calls = []

        def iter_messages(chat_id, limit=0, min_id=0, max_id=0):
            iter_calls.append((chat_id, limit, min_id, max_id))
            if max_id:
                return _chat_history([
                    _message(49, _media("older-a.mkv", 200)),
                    _message(48, _media("older-b.mkv", 300)),
                ])
            return _chat_history([
                _message(52, _media("newer-a.mkv", 400)),
                _message(51, _media("newer-b.mkv", 500)),
            ])

        client.iter_messages = iter_messages
        tc_mod._client = client

        result = await tc_mod.get_channel_messages(-1001234, around=50, limit=3)

        assert [m["message_id"] for m in result["messages"]] == [52, 51, 50, 49, 48]
        assert result["messages"][2]["caption"] == "mismatch found"
        client.get_messages.assert_awaited_once_with(-1001234, 50)
        assert iter_calls[0] == (-1001234, 3, 50, 0)
        assert iter_calls[1] == (-1001234, 4, 0, 50)

    async def test_around_message_filters_history_by_topic(self):
        client = AsyncMock()
        found = _message(50, _media("found.mkv", 100), topic_id=500)
        client.get_messages = AsyncMock(return_value=found)

        iter_calls = []

        def iter_messages(chat_id, limit=0, min_id=0, max_id=0, reply_to=None):
            iter_calls.append((chat_id, limit, min_id, max_id, reply_to))
            if max_id:
                return _chat_history([
                    _message(49, _media("same-topic.mkv", 200), topic_id=500),
                    _message(48, _media("other-topic.mkv", 300), topic_id=600),
                    _message(47, _media("same-topic-2.mkv", 400), topic_id=500),
                ])
            return _chat_history([])

        client.iter_messages = iter_messages
        tc_mod._client = client

        result = await tc_mod.get_channel_messages(-1001234, around=50, limit=3)

        assert result["topic_id"] == 500
        assert [message["message_id"] for message in result["messages"]] == [50, 49, 47]
        assert iter_calls == [(-1001234, 4, 50, 0, 500), (-1001234, 4, 0, 50, 500)]

    async def test_topic_filter_matches_reply_to_message_id_history(self):
        client = AsyncMock()
        found = _message(50, _media("found.mkv", 100), topic_id=500)
        client.get_messages = AsyncMock(return_value=found)

        def iter_messages(chat_id, limit=0, min_id=0, max_id=0, reply_to=None):
            if max_id:
                return _chat_history([
                    _message_with_reply_id(49, _media("same-topic.mkv", 200), reply_to_message_id=500),
                    _message_with_reply_id(48, _media("other-topic.mkv", 300), reply_to_message_id=600),
                    _message_with_reply_id(47, _media("same-topic-2.mkv", 400), reply_to_message_id=500),
                ])
            return _chat_history([])

        client.iter_messages = iter_messages
        tc_mod._client = client

        result = await tc_mod.get_channel_messages(-1001234, around=50, limit=3)

        assert result["topic_id"] == 500
        assert [message["message_id"] for message in result["messages"]] == [50, 49, 47]

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
                "topic_id": None,
                "telegram_url": "https://t.me/series/30",
                "sender_name": "Uploader",
                "date": "2025-01-01T12:30:00+00:00",
                "filename": "a.mkv",
                "file_size": 100,
                "mime_type": "video/x-matroska",
                "downloadable": True,
                "media_group_id": None,
                "text": None,
                "caption": None,
                "body": None,
                "thumbnail_url": None,
            },
            {
                "message_id": 28,
                "topic_id": None,
                "telegram_url": "https://t.me/series/28",
                "sender_name": "Uploader",
                "date": "2025-01-01T12:28:00+00:00",
                "filename": "b.mkv",
                "file_size": 200,
                "mime_type": "video/x-matroska",
                "downloadable": True,
                "media_group_id": None,
                "text": None,
                "caption": None,
                "body": None,
                "thumbnail_url": None,
            },
        ]
        assert result["has_older"] is True
        assert result["older_cursor"] == 28
        assert result["has_newer"] is True
        assert result["newer_cursor"] == 30
        assert history_calls == [(-1001234, 3, 31)]

    async def test_returns_text_only_messages(self):
        client = AsyncMock()
        client.get_chat_history = lambda chat_id, limit, offset_id=0: _chat_history([
            _message(30, None, text="plain channel update"),
        ])
        tc_mod._client = client

        result = await tc_mod.get_channel_messages(-1001234, limit=20)

        assert result["messages"] == [
            {
                "message_id": 30,
                "topic_id": None,
                "telegram_url": "https://t.me/series/30",
                "sender_name": "Uploader",
                "date": "2025-01-01T12:30:00+00:00",
                "filename": None,
                "file_size": None,
                "mime_type": None,
                "downloadable": False,
                "media_group_id": None,
                "text": "plain channel update",
                "caption": None,
                "body": "plain channel update",
                "thumbnail_url": None,
            },
        ]

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
        assert result["has_older"] is False
        assert result["older_cursor"] is None
        assert result["has_newer"] is False
        assert result["newer_cursor"] is None
        assert history_calls == [(-1001234, 21, 0)]

    async def test_topic_pagination_uses_reply_to_instead_of_scanning_channel_history(self):
        client = AsyncMock()
        iter_calls = []

        def iter_messages(chat_id, limit=0, offset_id=0, reply_to=None):
            iter_calls.append((chat_id, limit, offset_id, reply_to))
            return _chat_history([
                _message(10, _media("a.mkv"), topic_id=998),
                _message(9, _media("b.mkv"), topic_id=998),
                _message(8, _media("c.mkv"), topic_id=998),
            ])

        client.iter_messages = iter_messages
        client.get_chat_history = AsyncMock()

        tc_mod._client = client
        result = await tc_mod.get_channel_messages(-1001234, before=11, limit=2, topic_id=998)

        assert [message["message_id"] for message in result["messages"]] == [10, 9]
        assert result["has_older"] is True
        assert result["older_cursor"] == 9
        assert result["has_newer"] is True
        assert result["newer_cursor"] == 10
        assert iter_calls == [(-1001234, 3, 11, 998)]
        client.get_chat_history.assert_not_called()

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
