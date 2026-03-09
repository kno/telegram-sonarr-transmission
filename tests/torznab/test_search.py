import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.torznab.search import (
    _extract_media_info,
    _build_link,
    _filter_by_season_ep,
    _build_rss_response,
    _search_channel,
    do_search,
)


# ---------------------------------------------------------------------------
# Unit tests: pure helpers
# ---------------------------------------------------------------------------

class TestExtractMediaInfo:
    def test_with_document(self, mock_message):
        msg = mock_message(file_name="video.mkv", file_size=1000, mime_type="video/x-matroska")
        result = _extract_media_info(msg)
        assert result["filename"] == "video.mkv"
        assert result["size"] == 1000
        assert result["mime_type"] == "video/x-matroska"

    def test_no_document(self, mock_message):
        msg = mock_message(has_document=False)
        assert _extract_media_info(msg) is None

    def test_missing_fields(self):
        msg = MagicMock()
        msg.document.file_name = None
        msg.document.file_size = None
        msg.document.mime_type = None
        result = _extract_media_info(msg)
        assert result["filename"] is None
        assert result["size"] == 0
        assert result["mime_type"] == "application/octet-stream"


class TestBuildLink:
    def test_with_username(self):
        chat = MagicMock()
        chat.username = "mychannel"
        assert _build_link(chat, 42) == "https://t.me/mychannel/42"

    def test_without_username(self):
        chat = MagicMock()
        chat.username = None
        chat.id = 1234567
        assert _build_link(chat, 42) == "https://t.me/c/1234567/42"


class TestFilterBySeasonEp:
    @pytest.mark.parametrize("title,season,ep,should_match", [
        ("Show.S02E03.720p.mkv", "2", "3", True),
        ("Show.s2e3.720p.mkv", "2", "3", True),
        ("Show.2x03.720p.mkv", "2", "3", True),
        ("Show.02x03.720p.mkv", "2", "3", True),
        ("Show.S02E03.720p.mkv", "1", "3", False),
        ("Show.S02E03.720p.mkv", "2", "4", False),
        ("Show.S02E03.720p.mkv", "2", None, True),
        ("Show.S03E01.720p.mkv", "2", None, False),
        ("random_file.mkv", "2", "3", False),
        ("Show.S10E05.720p.mkv", "10", "5", True),
        ("Show.2x03.720p.mkv", "2", None, True),
    ])
    def test_parametrized(self, title, season, ep, should_match):
        items = [{"title": title}]
        result = _filter_by_season_ep(items, season, ep)
        assert (len(result) == 1) == should_match

    def test_mixed_items(self):
        items = [
            {"title": "Show.S02E03.720p.mkv"},
            {"title": "Show.S02E04.720p.mkv"},
            {"title": "Other.S01E01.mkv"},
        ]
        result = _filter_by_season_ep(items, "2", "3")
        assert len(result) == 1
        assert result[0]["title"] == "Show.S02E03.720p.mkv"

    def test_no_season_no_ep_returns_empty(self):
        items = [{"title": "Show.S02E03.mkv"}]
        result = _filter_by_season_ep(items, None, None)
        assert result == []


class TestBuildRssResponse:
    def test_empty(self, test_settings):
        resp = _build_rss_response([], 0, 0)
        root = ET.fromstring(resp.body.decode())
        assert root.tag == "rss"
        channel = root.find("channel")
        assert channel is not None

    def test_with_items(self, test_settings):
        items = [{
            "title": "Test.S01E01.mkv",
            "guid": "-100:1",
            "link": "https://t.me/test/1",
            "chat_id": "-100",
            "msg_id": 1,
            "pub_date": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "size": 1000,
            "category_id": 1000,
            "description": "test",
        }]
        resp = _build_rss_response(items, 1, 0)
        root = ET.fromstring(resp.body.decode())
        channel = root.find("channel")
        xml_items = channel.findall("item")
        assert len(xml_items) == 1
        assert xml_items[0].find("title").text == "Test.S01E01.mkv"
        enclosure = xml_items[0].find("enclosure")
        assert enclosure is not None
        assert enclosure.get("type") == "application/x-bittorrent"

    def test_pagination_offset(self, test_settings):
        resp = _build_rss_response([], 10, 5)
        root = ET.fromstring(resp.body.decode())
        ns = {"newznab": "http://www.newznab.com/DTD/2010/feeds/attributes/"}
        response_elem = root.find(".//newznab:response", ns)
        assert response_elem.get("offset") == "5"
        assert response_elem.get("total") == "10"


# ---------------------------------------------------------------------------
# Integration tests: search pipeline (mocked Telegram)
# ---------------------------------------------------------------------------

class TestSearchChannel:
    async def test_success(self, test_settings, mock_telegram_client, populated_channels, mock_message):
        msg = mock_message(msg_id=1, file_name="Show.S01E01.mkv", file_size=5000)
        chat_mock = MagicMock()
        chat_mock.username = "testchan"
        mock_telegram_client.get_chat = AsyncMock(return_value=chat_mock)

        async def fake_search(chat_id, query, limit):
            yield msg

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        items = await _search_channel("-1001234", "Show", 10)
        assert len(items) == 1
        assert items[0]["title"] == "Show.S01E01.mkv"

    async def test_no_results(self, test_settings, mock_telegram_client, populated_channels):
        chat_mock = MagicMock()
        chat_mock.username = "testchan"
        mock_telegram_client.get_chat = AsyncMock(return_value=chat_mock)

        async def empty_search(chat_id, query, limit):
            return
            yield

        mock_telegram_client.search_messages = MagicMock(side_effect=empty_search)
        items = await _search_channel("-1001234", "nothing", 10)
        assert items == []

    async def test_error_returns_empty(self, test_settings, mock_telegram_client, populated_channels):
        mock_telegram_client.get_chat = AsyncMock(side_effect=Exception("Flood wait"))
        items = await _search_channel("-1001234", "test", 10)
        assert items == []


class TestDoSearch:
    async def test_by_category(self, test_settings, mock_telegram_client, populated_channels, mock_message):
        msg = mock_message(msg_id=1, file_name="Result.mkv", file_size=1000)
        chat_mock = MagicMock()
        chat_mock.username = "testchan"
        mock_telegram_client.get_chat = AsyncMock(return_value=chat_mock)

        async def fake_search(chat_id, query, limit):
            yield msg

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        resp = await do_search("Result", "1000", 0, 50)
        root = ET.fromstring(resp.body.decode())
        items = root.findall(".//item")
        assert len(items) == 1

    async def test_empty_query_limits_channels(self, test_settings, mock_telegram_client, populated_channels, monkeypatch):
        # With 2 channels and no query, both should be searched (< 5 limit)
        search_calls = []

        async def fake_search(chat_id, query, limit):
            search_calls.append(chat_id)
            return
            yield

        mock_telegram_client.get_chat = AsyncMock(return_value=MagicMock(username="x"))
        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        await do_search(None, None, 0, 50)
        assert len(search_calls) == 2  # Both channels searched (< 5 limit)

    async def test_with_season_episode_filter(self, test_settings, mock_telegram_client, populated_channels, mock_message):
        msgs = [
            mock_message(msg_id=1, file_name="Show.S02E03.mkv", file_size=1000),
            mock_message(msg_id=2, file_name="Show.S02E04.mkv", file_size=1000),
        ]
        chat_mock = MagicMock()
        chat_mock.username = "testchan"
        mock_telegram_client.get_chat = AsyncMock(return_value=chat_mock)

        async def fake_search(chat_id, query, limit):
            for m in msgs:
                yield m

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        resp = await do_search("Show", "1000", 0, 50, season="2", ep="3")
        root = ET.fromstring(resp.body.decode())
        items = root.findall(".//item")
        assert len(items) == 1
        assert "S02E03" in items[0].find("title").text
