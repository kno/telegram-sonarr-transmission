import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.transmission.downloader as dl_mod
from app.transmission.downloader import (
    enqueue_download,
    _download_from_telegram,
    resume_downloads,
)
from app.transmission.state import get_downloads


@pytest.fixture(autouse=True)
def _reset_state():
    import app.transmission.state as state_mod
    old_downloads = dict(state_mod._downloads)
    old_next_id = state_mod._next_id
    state_mod._downloads.clear()
    state_mod._next_id = 1
    yield
    state_mod._downloads.clear()
    state_mod._downloads.update(old_downloads)
    state_mod._next_id = old_next_id


@pytest.fixture(autouse=True)
def _reset_downloader():
    old_tasks = dict(dl_mod._active_tasks)
    old_queue = dl_mod._download_queue
    old_worker = dl_mod._worker_task
    dl_mod._active_tasks.clear()
    dl_mod._download_queue = None
    dl_mod._worker_task = None
    yield
    dl_mod._active_tasks.clear()
    dl_mod._active_tasks.update(old_tasks)
    dl_mod._download_queue = old_queue
    dl_mod._worker_task = old_worker


@pytest.fixture(autouse=True)
def _mock_broadcast(monkeypatch):
    monkeypatch.setattr("app.transmission.downloader.broadcast_downloads", AsyncMock())


@pytest.fixture(autouse=True)
def _mock_save(monkeypatch):
    monkeypatch.setattr("app.transmission.downloader.save_state", lambda: None)
    monkeypatch.setattr("app.transmission.state.save_state", lambda: None)


class TestEnqueueDownload:
    async def test_sets_status_queued(self, test_settings, monkeypatch):
        # Mock _ensure_queue to avoid creating background worker
        monkeypatch.setattr("app.transmission.downloader._ensure_queue", lambda: None)
        dl_mod._download_queue = asyncio.Queue()
        downloads = get_downloads()
        downloads[1] = {"id": 1, "status": 0}
        enqueue_download(1)
        assert downloads[1]["status"] == 3


class TestDownloadFromTelegram:
    async def test_success(self, test_settings, mock_telegram_client, mock_message, tmp_path):
        msg = mock_message(msg_id=1, file_name="video.mkv", file_size=10)
        mock_telegram_client.get_messages = AsyncMock(return_value=msg)

        async def fake_stream(message, offset=0):
            yield b"0123456789"

        mock_telegram_client.stream_media = MagicMock(side_effect=fake_stream)

        download_dir = str(tmp_path / "dl")
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "chat_id": "-100", "msg_id": 1,
            "name": "video.mkv", "downloadDir": download_dir,
            "status": 4, "_start_time": 0,
        }

        await _download_from_telegram(1)

        assert downloads[1]["status"] == 6
        assert downloads[1]["isFinished"] is True
        assert downloads[1]["percentDone"] == 1.0
        assert os.path.exists(os.path.join(download_dir, "video.mkv"))

    async def test_no_document(self, test_settings, mock_telegram_client, mock_message):
        msg = mock_message(has_document=False)
        mock_telegram_client.get_messages = AsyncMock(return_value=msg)

        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "chat_id": "-100", "msg_id": 1,
            "name": "test", "downloadDir": "/tmp/test",
            "status": 4, "_start_time": 0,
        }

        await _download_from_telegram(1)
        assert downloads[1]["error"] == 1
        assert downloads[1]["status"] == 0

    async def test_error_handling(self, test_settings, mock_telegram_client):
        mock_telegram_client.get_messages = AsyncMock(side_effect=Exception("Network error"))

        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "chat_id": "-100", "msg_id": 1,
            "name": "test", "downloadDir": "/tmp/test",
            "status": 4, "_start_time": 0,
        }

        await _download_from_telegram(1)
        assert downloads[1]["error"] == 1
        assert "Network error" in downloads[1]["errorString"]
        assert downloads[1]["status"] == 0

    async def test_resume_with_tmp(self, test_settings, mock_telegram_client, mock_message, tmp_path):
        msg = mock_message(msg_id=1, file_name="video.mkv", file_size=2 * 1024 * 1024)
        mock_telegram_client.get_messages = AsyncMock(return_value=msg)

        download_dir = str(tmp_path / "dl")
        os.makedirs(download_dir, exist_ok=True)
        tmp_file = os.path.join(download_dir, "video.mkv.tmp")
        # Write exactly 1MB (1 chunk aligned)
        with open(tmp_file, "wb") as f:
            f.write(b"\x00" * (1024 * 1024))

        chunk2 = b"\x01" * (1024 * 1024)

        async def fake_stream(message, offset=0):
            assert offset == 1  # Should resume from chunk 1
            yield chunk2

        mock_telegram_client.stream_media = MagicMock(side_effect=fake_stream)

        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "chat_id": "-100", "msg_id": 1,
            "name": "video.mkv", "downloadDir": download_dir,
            "status": 4, "_start_time": 0,
        }

        await _download_from_telegram(1)
        assert downloads[1]["isFinished"] is True
        final_path = os.path.join(download_dir, "video.mkv")
        assert os.path.exists(final_path)
        assert os.path.getsize(final_path) == 2 * 1024 * 1024

    async def test_stale_tmp_removed(self, test_settings, mock_telegram_client, mock_message, tmp_path):
        # tmp file larger than actual file size -> should be removed
        msg = mock_message(msg_id=1, file_name="video.mkv", file_size=100)
        mock_telegram_client.get_messages = AsyncMock(return_value=msg)

        download_dir = str(tmp_path / "dl")
        os.makedirs(download_dir, exist_ok=True)
        tmp_file = os.path.join(download_dir, "video.mkv.tmp")
        with open(tmp_file, "wb") as f:
            f.write(b"\x00" * 200)  # Larger than file_size

        async def fake_stream(message, offset=0):
            assert offset == 0  # Fresh start
            yield b"\x01" * 100

        mock_telegram_client.stream_media = MagicMock(side_effect=fake_stream)

        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "chat_id": "-100", "msg_id": 1,
            "name": "video.mkv", "downloadDir": download_dir,
            "status": 4, "_start_time": 0,
        }

        await _download_from_telegram(1)
        assert downloads[1]["isFinished"] is True

    async def test_missing_torrent_id(self, test_settings):
        # Should return silently
        await _download_from_telegram(999)


class TestResumeDownloads:
    async def test_resumes_incomplete(self, test_settings, monkeypatch):
        enqueue_calls = []
        monkeypatch.setattr("app.transmission.downloader.enqueue_download", lambda tid: enqueue_calls.append(tid))
        monkeypatch.setattr("app.transmission.downloader.load_state", lambda: None)

        downloads = get_downloads()
        downloads[1] = {"id": 1, "status": 4, "isFinished": False, "name": "test", "rateDownload": 100}
        downloads[2] = {"id": 2, "status": 3, "isFinished": False, "name": "queued"}

        await resume_downloads()

        assert 1 in enqueue_calls
        assert 2 in enqueue_calls
        assert downloads[1]["rateDownload"] == 0

    async def test_skips_finished(self, test_settings, monkeypatch):
        enqueue_calls = []
        monkeypatch.setattr("app.transmission.downloader.enqueue_download", lambda tid: enqueue_calls.append(tid))
        monkeypatch.setattr("app.transmission.downloader.load_state", lambda: None)

        downloads = get_downloads()
        downloads[1] = {"id": 1, "status": 6, "isFinished": True, "name": "done"}

        await resume_downloads()
        assert enqueue_calls == []

    async def test_skips_stopped(self, test_settings, monkeypatch):
        enqueue_calls = []
        monkeypatch.setattr("app.transmission.downloader.enqueue_download", lambda tid: enqueue_calls.append(tid))
        monkeypatch.setattr("app.transmission.downloader.load_state", lambda: None)

        downloads = get_downloads()
        downloads[1] = {"id": 1, "status": 0, "isFinished": False, "name": "stopped"}

        await resume_downloads()
        assert enqueue_calls == []
