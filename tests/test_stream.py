import os
import xml.etree.ElementTree as ET
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.stream import _find_cached_file


class TestFindCachedFile:
    def test_exists(self, test_settings, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "-100_42_video.mkv").write_bytes(b"data")
        result = _find_cached_file("-100", "42")
        assert result is not None
        assert result.endswith("-100_42_video.mkv")

    def test_not_found(self, test_settings, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        assert _find_cached_file("-100", "42") is None

    def test_no_directory(self, test_settings):
        assert _find_cached_file("-100", "42") is None


class TestStreamRouter:
    async def test_cached_file(self, async_client, test_settings, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        content = b"x" * 100
        (cache_dir / "-100_42_video.mkv").write_bytes(content)

        resp = await async_client.get("/api/stream", params={
            "id": "-100:42",
            "apikey": "testapikey",
        })
        assert resp.status_code == 200
        assert len(resp.content) == 100

    async def test_range_request(self, async_client, test_settings, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        content = b"0123456789" * 10  # 100 bytes
        (cache_dir / "-100_42_video.mkv").write_bytes(content)

        resp = await async_client.get(
            "/api/stream",
            params={"id": "-100:42", "apikey": "testapikey"},
            headers={"Range": "bytes=10-19"},
        )
        assert resp.status_code == 206
        assert len(resp.content) == 10
        assert "bytes 10-19/100" in resp.headers["content-range"]

    async def test_range_to_end(self, async_client, test_settings, tmp_path):
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        content = b"x" * 50
        (cache_dir / "-100_42_video.mkv").write_bytes(content)

        resp = await async_client.get(
            "/api/stream",
            params={"id": "-100:42", "apikey": "testapikey"},
            headers={"Range": "bytes=40-"},
        )
        assert resp.status_code == 206
        assert len(resp.content) == 10

    async def test_fallback_downloads_from_telegram(self, async_client, test_settings, mock_telegram_client, mock_message, tmp_path):
        msg = mock_message(msg_id=42, file_name="video.mkv", file_size=100)
        mock_telegram_client.get_messages = AsyncMock(return_value=msg)

        # download_media should create the file
        cache_dir = tmp_path / "cache"

        async def fake_download(message, file_name=None):
            os.makedirs(os.path.dirname(file_name), exist_ok=True)
            with open(file_name, "wb") as f:
                f.write(b"telegram_content")

        mock_telegram_client.download_media = AsyncMock(side_effect=fake_download)

        resp = await async_client.get("/api/stream", params={
            "id": "-100:42",
            "apikey": "testapikey",
        })
        assert resp.status_code == 200
        assert resp.content == b"telegram_content"

    async def test_bad_apikey(self, async_client):
        resp = await async_client.get("/api/stream", params={
            "id": "-100:42",
            "apikey": "wrong",
        })
        root = ET.fromstring(resp.text)
        assert root.get("code") == "100"

    async def test_invalid_id(self, async_client):
        resp = await async_client.get("/api/stream", params={
            "id": "badformat",
            "apikey": "testapikey",
        })
        root = ET.fromstring(resp.text)
        assert root.get("code") == "201"

    async def test_message_not_found(self, async_client, mock_telegram_client):
        mock_telegram_client.get_messages = AsyncMock(side_effect=Exception("Error"))
        resp = await async_client.get("/api/stream", params={
            "id": "-100:42",
            "apikey": "testapikey",
        })
        root = ET.fromstring(resp.text)
        assert root.get("code") == "300"

    async def test_no_document(self, async_client, mock_telegram_client, mock_message):
        msg = mock_message(has_document=False)
        mock_telegram_client.get_messages = AsyncMock(return_value=msg)
        resp = await async_client.get("/api/stream", params={
            "id": "-100:42",
            "apikey": "testapikey",
        })
        root = ET.fromstring(resp.text)
        assert root.get("code") == "300"
