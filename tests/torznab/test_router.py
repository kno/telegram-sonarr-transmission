import xml.etree.ElementTree as ET

import pytest


class TestTorznabRouter:
    async def test_caps_no_auth(self, async_client):
        resp = await async_client.get("/api", params={"t": "caps"})
        assert resp.status_code == 200
        root = ET.fromstring(resp.text)
        assert root.tag == "caps"

    async def test_search_valid(self, async_client, mock_telegram_client, mock_message):
        from unittest.mock import AsyncMock, MagicMock
        msg = mock_message(msg_id=1, file_name="Result.mkv", file_size=1000)
        chat_mock = MagicMock()
        chat_mock.username = "test"
        mock_telegram_client.get_chat = AsyncMock(return_value=chat_mock)

        async def fake_search(chat_id, query, limit):
            yield msg

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        resp = await async_client.get("/api", params={"t": "search", "q": "test", "apikey": "testapikey"})
        assert resp.status_code == 200
        root = ET.fromstring(resp.text)
        assert root.tag == "rss"

    async def test_search_bad_apikey(self, async_client):
        resp = await async_client.get("/api", params={"t": "search", "q": "test", "apikey": "wrong"})
        root = ET.fromstring(resp.text)
        assert root.get("code") == "100"

    async def test_search_no_apikey(self, async_client):
        resp = await async_client.get("/api", params={"t": "search", "q": "test"})
        root = ET.fromstring(resp.text)
        assert root.get("code") == "100"

    async def test_tvsearch(self, async_client, mock_telegram_client):
        from unittest.mock import AsyncMock, MagicMock
        mock_telegram_client.get_chat = AsyncMock(return_value=MagicMock(username="x"))

        async def empty(chat_id, query, limit):
            return
            yield

        mock_telegram_client.search_messages = MagicMock(side_effect=empty)
        resp = await async_client.get("/api", params={"t": "tvsearch", "q": "test", "apikey": "testapikey"})
        assert resp.status_code == 200
        root = ET.fromstring(resp.text)
        assert root.tag == "rss"

    async def test_unknown_function(self, async_client):
        resp = await async_client.get("/api", params={"t": "unknown", "apikey": "testapikey"})
        root = ET.fromstring(resp.text)
        assert root.get("code") == "202"

    async def test_limit_clamped(self, async_client, mock_telegram_client, monkeypatch):
        from unittest.mock import AsyncMock, MagicMock
        from app.torznab import search as search_mod

        captured_limit = []
        original_do_search = search_mod.do_search

        async def capture_search(query, cat, offset, limit, **kw):
            captured_limit.append(limit)
            return await original_do_search(query, cat, offset, limit, **kw)

        monkeypatch.setattr("app.torznab.router.do_search", capture_search)
        mock_telegram_client.get_chat = AsyncMock(return_value=MagicMock(username="x"))

        async def empty(chat_id, query, limit):
            return
            yield

        mock_telegram_client.search_messages = MagicMock(side_effect=empty)
        await async_client.get("/api", params={"t": "search", "q": "x", "apikey": "testapikey", "limit": "999"})
        assert captured_limit[0] == 100  # MAX_LIMIT
