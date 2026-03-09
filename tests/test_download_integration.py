import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.download import _bdecode


class TestDownloadRouter:
    async def test_success(self, async_client, mock_telegram_client, mock_message):
        msg = mock_message(msg_id=42, file_name="video.mkv", file_size=1048576)
        mock_telegram_client.get_messages = AsyncMock(return_value=msg)

        resp = await async_client.get("/api/download", params={
            "id": "-100:42",
            "apikey": "testapikey",
        })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/x-bittorrent"
        assert "video.mkv.torrent" in resp.headers["content-disposition"]

        torrent = _bdecode(resp.content)
        assert torrent[b"comment"] == b"-100:42"
        assert torrent[b"info"][b"name"] == b"video.mkv"

    async def test_bad_apikey(self, async_client):
        resp = await async_client.get("/api/download", params={
            "id": "-100:42",
            "apikey": "wrong",
        })
        assert resp.status_code == 200
        root = ET.fromstring(resp.text)
        assert root.get("code") == "100"

    async def test_invalid_id_format(self, async_client):
        resp = await async_client.get("/api/download", params={
            "id": "notvalid",
            "apikey": "testapikey",
        })
        root = ET.fromstring(resp.text)
        assert root.get("code") == "201"

    async def test_non_numeric_ids(self, async_client):
        resp = await async_client.get("/api/download", params={
            "id": "abc:def",
            "apikey": "testapikey",
        })
        root = ET.fromstring(resp.text)
        assert root.get("code") == "201"

    async def test_message_not_found(self, async_client, mock_telegram_client):
        mock_telegram_client.get_messages = AsyncMock(side_effect=Exception("Not found"))
        resp = await async_client.get("/api/download", params={
            "id": "-100:42",
            "apikey": "testapikey",
        })
        root = ET.fromstring(resp.text)
        assert root.get("code") == "300"

    async def test_no_document(self, async_client, mock_telegram_client, mock_message):
        msg = mock_message(has_document=False)
        mock_telegram_client.get_messages = AsyncMock(return_value=msg)
        resp = await async_client.get("/api/download", params={
            "id": "-100:42",
            "apikey": "testapikey",
        })
        root = ET.fromstring(resp.text)
        assert root.get("code") == "300"
