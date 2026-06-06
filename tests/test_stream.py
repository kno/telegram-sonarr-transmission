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


# ===================================================================
# Task 1.4 / 1.7: Stream resolution via state
# ===================================================================

class TestStreamResolvesFromState:
    async def test_stream_resolves_from_file_path_in_state(
        self, async_client, test_settings, clean_downloads, tmp_path
    ):
        """When state has a download with file_path, stream should use it directly."""
        # Seed a download in state
        import app.transmission.state as state_mod
        state_mod._downloads[1] = {
            "id": 1,
            "name": "video.mkv",
            "chat_id": "-100",
            "msg_id": 42,
            "downloadDir": str(tmp_path),
            "file_path": str(tmp_path / "video.mkv"),
            "status": 6,
        }
        # Create the actual file at the path
        (tmp_path / "video.mkv").write_bytes(b"state_resolved_content")

        resp = await async_client.get("/api/stream", params={
            "id": "-100:42",
            "apikey": "testapikey",
        })
        assert resp.status_code == 200
        assert resp.content == b"state_resolved_content"

    async def test_stream_resolves_from_download_dir_when_no_file_path(
        self, async_client, test_settings, clean_downloads, tmp_path
    ):
        """When state has a download but no file_path, resolve via downloadDir + name."""
        import app.transmission.state as state_mod
        # Don't set file_path — fallback to downloadDir + name
        state_mod._downloads[1] = {
            "id": 1,
            "name": "video.mkv",
            "chat_id": "-100",
            "msg_id": 43,
            "downloadDir": str(tmp_path / "cache"),
            "status": 6,
        }
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "video.mkv").write_bytes(b"download_dir_content")

        resp = await async_client.get("/api/stream", params={
            "id": "-100:43",
            "apikey": "testapikey",
        })
        assert resp.status_code == 200
        assert resp.content == b"download_dir_content"

    async def test_stream_falls_back_to_scan_when_no_state_match(
        self, async_client, test_settings, clean_downloads, tmp_path
    ):
        """When state has no match, fall back to scanning DOWNLOAD_DIR."""
        # Create file in DOWNLOAD_DIR
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "-100_44_video.mkv").write_bytes(b"scan_fallback")

        resp = await async_client.get("/api/stream", params={
            "id": "-100:44",
            "apikey": "testapikey",
        })
        assert resp.status_code == 200
        assert resp.content == b"scan_fallback"

    async def test_stream_prefers_file_path_over_download_dir(
        self, async_client, test_settings, clean_downloads, tmp_path
    ):
        """When both file_path and downloadDir are set, file_path wins."""
        import app.transmission.state as state_mod
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)
        moved_dir = tmp_path / "moved"
        moved_dir.mkdir()

        # A stale file in DOWNLOAD_DIR
        (cache_dir / "-100_45_video.mkv").write_bytes(b"stale_cache")
        # The actual file at the new location
        (moved_dir / "video.mkv").write_bytes(b"moved_location")

        state_mod._downloads[1] = {
            "id": 1,
            "name": "video.mkv",
            "chat_id": "-100",
            "msg_id": 45,
            "downloadDir": str(cache_dir),
            "file_path": str(moved_dir / "video.mkv"),
            "status": 6,
        }

        resp = await async_client.get("/api/stream", params={
            "id": "-100:45",
            "apikey": "testapikey",
        })
        assert resp.status_code == 200
        assert resp.content == b"moved_location"

    async def test_state_file_path_but_file_missing_still_serves_from_download_dir(
        self, async_client, test_settings, clean_downloads, tmp_path
    ):
        """If file_path points to a missing file, fall back to downloadDir + name."""
        import app.transmission.state as state_mod
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "video.mkv").write_bytes(b"fallback_from_download_dir")

        # file_path points to nonexistent file
        nonexistent = tmp_path / "nonexistent" / "video.mkv"
        state_mod._downloads[1] = {
            "id": 1,
            "name": "video.mkv",
            "chat_id": "-100",
            "msg_id": 46,
            "downloadDir": str(cache_dir),
            "file_path": str(nonexistent),
            "status": 6,
        }

        resp = await async_client.get("/api/stream", params={
            "id": "-100:46",
            "apikey": "testapikey",
        })
        assert resp.status_code == 200
        assert resp.content == b"fallback_from_download_dir"
