import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.download import _bencode, create_minimal_torrent
from app.transmission.handlers import (
    session_get,
    session_stats,
    torrent_add,
    torrent_get,
    torrent_remove,
    torrent_stop,
    torrent_start,
    torrent_set,
)
from app.transmission.state import get_downloads, get_next_id


@pytest.fixture(autouse=True)
def _reset_state():
    import app.transmission.state as mod
    old_downloads = dict(mod._downloads)
    old_next_id = mod._next_id
    mod._downloads.clear()
    mod._next_id = 1
    yield
    mod._downloads.clear()
    mod._downloads.update(old_downloads)
    mod._next_id = old_next_id


@pytest.fixture(autouse=True)
def _mock_enqueue(monkeypatch):
    monkeypatch.setattr("app.transmission.handlers.enqueue_download", lambda tid: None)


@pytest.fixture(autouse=True)
def _mock_broadcast(monkeypatch):
    monkeypatch.setattr("app.transmission.handlers.broadcast_downloads", AsyncMock())


class TestSessionGet:
    async def test_returns_fields(self, test_settings):
        result = await session_get({})
        assert result["version"] == "4.0.0 (telegram-torznab)"
        assert result["rpc-version"] == 17
        assert result["download-dir"] == test_settings.DOWNLOAD_DIR


class TestSessionStats:
    async def test_empty(self):
        result = await session_stats({})
        assert result["activeTorrentCount"] == 0
        assert result["torrentCount"] == 0

    async def test_with_downloads(self):
        downloads = get_downloads()
        downloads[1] = {"status": 4, "rateDownload": 1000}
        downloads[2] = {"status": 0, "rateDownload": 0}
        downloads[3] = {"status": 3, "rateDownload": 500}
        result = await session_stats({})
        assert result["activeTorrentCount"] == 2
        assert result["pausedTorrentCount"] == 1
        assert result["torrentCount"] == 3
        assert result["downloadSpeed"] == 1500


class TestTorrentAdd:
    def _make_metainfo(self, chat_id="-100", msg_id=42, name="test.mkv", size=1000):
        torrent_bytes = create_minimal_torrent(name, size, chat_id, msg_id)
        return base64.b64encode(torrent_bytes).decode()

    async def test_success(self, test_settings):
        result = await torrent_add({"metainfo": self._make_metainfo()})
        assert "torrent-added" in result
        added = result["torrent-added"]
        assert added["name"] == "test.mkv"
        assert added["id"] == 1
        downloads = get_downloads()
        assert 1 in downloads
        assert downloads[1]["chat_id"] == "-100"
        assert downloads[1]["msg_id"] == 42

    async def test_no_metainfo(self, test_settings):
        result = await torrent_add({"metainfo": ""})
        assert result == {"torrent-duplicate": None}

    async def test_duplicate(self, test_settings):
        metainfo = self._make_metainfo()
        await torrent_add({"metainfo": metainfo})
        result = await torrent_add({"metainfo": metainfo})
        assert "torrent-duplicate" in result
        assert result["torrent-duplicate"]["id"] == 1

    async def test_invalid_torrent(self, test_settings):
        result = await torrent_add({"metainfo": "not_base64!!!"})
        assert result == {"torrent-duplicate": None}

    async def test_no_comment(self, test_settings):
        torrent = _bencode({b"info": {b"name": b"test", b"length": 0, b"piece length": 512, b"pieces": b"\x00" * 20}})
        metainfo = base64.b64encode(torrent).decode()
        result = await torrent_add({"metainfo": metainfo})
        assert result == {"torrent-duplicate": None}

    async def test_custom_download_dir(self, test_settings, tmp_path):
        custom_dir = str(tmp_path / "custom")
        result = await torrent_add({
            "metainfo": self._make_metainfo(),
            "download-dir": custom_dir,
        })
        assert get_downloads()[1]["downloadDir"] == custom_dir


class TestTorrentGet:
    @pytest.fixture
    def _populate(self):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "file1.mkv", "status": 4, "_start_time": 999}
        downloads[2] = {"id": 2, "name": "file2.mkv", "status": 6, "_secret": "x"}

    async def test_all(self, _populate):
        result = await torrent_get({})
        assert len(result["torrents"]) == 2
        # Private keys filtered
        for t in result["torrents"]:
            assert "_start_time" not in t
            assert "_secret" not in t

    async def test_by_ids_list(self, _populate):
        result = await torrent_get({"ids": [1]})
        assert len(result["torrents"]) == 1
        assert result["torrents"][0]["name"] == "file1.mkv"

    async def test_by_ids_int(self, _populate):
        result = await torrent_get({"ids": 2})
        assert len(result["torrents"]) == 1
        assert result["torrents"][0]["name"] == "file2.mkv"

    async def test_with_fields(self, _populate):
        result = await torrent_get({"fields": ["name", "status"]})
        for t in result["torrents"]:
            assert set(t.keys()) <= {"name", "status"}

    async def test_missing_id(self):
        result = await torrent_get({"ids": [999]})
        assert result["torrents"] == []


class TestTorrentRemove:
    async def test_basic(self):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "test", "downloadDir": "/tmp", "status": 6}
        result = await torrent_remove({"ids": [1]})
        assert result == {}
        assert 1 not in downloads

    async def test_with_delete_data(self, tmp_path):
        file_path = tmp_path / "video.mkv"
        file_path.write_bytes(b"data")
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "video.mkv", "downloadDir": str(tmp_path), "status": 6}
        await torrent_remove({"ids": [1], "delete-local-data": True})
        assert not file_path.exists()

    async def test_cancels_active_task(self, monkeypatch):
        import app.transmission.downloader as dl_mod
        task = MagicMock()
        task.done.return_value = False
        old_tasks = dict(dl_mod._active_tasks)
        dl_mod._active_tasks[1] = task

        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "test", "downloadDir": "/tmp"}
        await torrent_remove({"ids": 1})
        task.cancel.assert_called_once()

        dl_mod._active_tasks.clear()
        dl_mod._active_tasks.update(old_tasks)

    async def test_ids_as_int(self):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "test", "downloadDir": "/tmp"}
        await torrent_remove({"ids": 1})
        assert 1 not in downloads


class TestTorrentStop:
    async def test_stop(self):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "status": 4, "rateDownload": 1000}
        await torrent_stop({"ids": [1]})
        assert downloads[1]["status"] == 0
        assert downloads[1]["rateDownload"] == 0


class TestTorrentStart:
    async def test_resumes(self, monkeypatch):
        enqueue_calls = []
        monkeypatch.setattr("app.transmission.handlers.enqueue_download", lambda tid: enqueue_calls.append(tid))
        downloads = get_downloads()
        downloads[1] = {"id": 1, "status": 0, "isFinished": False, "error": 1, "errorString": "prev err", "rateDownload": 0}
        await torrent_start({"ids": [1]})
        assert 1 in enqueue_calls
        assert downloads[1]["error"] == 0
        assert downloads[1]["errorString"] == ""

    async def test_skips_finished(self, monkeypatch):
        enqueue_calls = []
        monkeypatch.setattr("app.transmission.handlers.enqueue_download", lambda tid: enqueue_calls.append(tid))
        downloads = get_downloads()
        downloads[1] = {"id": 1, "status": 6, "isFinished": True}
        await torrent_start({"ids": [1]})
        assert enqueue_calls == []


class TestTorrentSet:
    async def test_noop(self):
        result = await torrent_set({})
        assert result == {}
