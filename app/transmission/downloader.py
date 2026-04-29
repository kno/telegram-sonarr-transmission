import asyncio
import logging
import os
import time

from app.config import settings
from app.media import extract_media_info
from app.telegram_client import get_client
from app.transmission.state import get_downloads, save_state, load_state
from app.transmission.websocket import broadcast_downloads, get_ws_clients

logger = logging.getLogger(__name__)

STREAM_CHUNK_SIZE = 1024 * 1024  # 1MB — Pyrogram's stream_media chunk size

_active_tasks: dict[int, asyncio.Task] = {}
_download_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None


def get_active_tasks() -> dict[int, asyncio.Task]:
    return _active_tasks


async def _queue_worker():
    """Process downloads one at a time from the queue."""
    downloads = get_downloads()
    while True:
        torrent_id = await _download_queue.get()
        info = downloads.get(torrent_id)
        if not info or info.get("isFinished") or info.get("status") == 0:
            _download_queue.task_done()
            continue

        info["status"] = 4  # TR_STATUS_DOWNLOAD
        info["_start_time"] = time.time()
        save_state()

        task = asyncio.create_task(_download_from_telegram(torrent_id))
        _active_tasks[torrent_id] = task
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        except Exception:
            pass
        _download_queue.task_done()


def _ensure_queue():
    """Initialize the download queue and worker if not already running."""
    global _download_queue, _worker_task
    if _download_queue is None:
        _download_queue = asyncio.Queue()
    if _worker_task is None or _worker_task.done():
        _worker_task = asyncio.create_task(_queue_worker())


def enqueue_download(torrent_id: int):
    """Add a download to the queue."""
    _ensure_queue()
    downloads = get_downloads()
    info = downloads.get(torrent_id)
    if info:
        info["status"] = 3  # TR_STATUS_CHECK_WAIT (queued)
        save_state()
    _download_queue.put_nowait(torrent_id)


async def _download_from_telegram(torrent_id: int):
    downloads = get_downloads()
    info = downloads.get(torrent_id)
    if not info:
        return

    try:
        client = get_client()
        message = await client.get_messages(int(info["chat_id"]), info["msg_id"])

        media_info = extract_media_info(message)
        if not media_info:
            info["error"] = 1
            info["errorString"] = "No media in message"
            info["status"] = 0
            save_state()
            return

        filename = media_info["filename"] or info["name"]
        file_size = media_info["size"]

        info["name"] = filename
        info["totalSize"] = file_size
        info["files"] = [{"name": filename, "length": file_size, "bytesCompleted": 0}]
        info["fileStats"] = [{"wanted": True, "priority": 0, "bytesCompleted": 0}]

        dest_path = os.path.join(info["downloadDir"], filename)
        os.makedirs(info["downloadDir"], exist_ok=True)
        tmp_path = dest_path + ".tmp"

        # Resume support: check existing .tmp file size
        downloaded = 0
        if os.path.exists(tmp_path):
            tmp_size = os.path.getsize(tmp_path)
            aligned = (tmp_size // STREAM_CHUNK_SIZE) * STREAM_CHUNK_SIZE
            if aligned > 0 and aligned < file_size:
                downloaded = aligned
                with open(tmp_path, "r+b") as f:
                    f.truncate(downloaded)
                logger.info(
                    "Resuming download at %.1f MB / %.1f MB: %s",
                    downloaded / 1048576, file_size / 1048576, filename,
                )
            else:
                os.remove(tmp_path)
                logger.info("Removed stale .tmp, starting fresh: %s", filename)

        info["downloadedEver"] = downloaded
        info["leftUntilDone"] = max(0, file_size - downloaded)
        info["percentDone"] = downloaded / file_size if file_size > 0 else 0
        info["files"][0]["bytesCompleted"] = downloaded
        info["fileStats"][0]["bytesCompleted"] = downloaded

        # Progress tracking
        last_save_time = time.time()
        last_speed_time = time.time()
        last_speed_received = downloaded
        last_broadcast_time = time.time()
        ws_clients = get_ws_clients()

        def _update_progress(total_received: int):
            nonlocal last_save_time, last_speed_time, last_speed_received, last_broadcast_time
            now = time.time()

            info["downloadedEver"] = total_received
            info["leftUntilDone"] = max(0, file_size - total_received)
            info["percentDone"] = total_received / file_size if file_size > 0 else 0
            info["files"][0]["bytesCompleted"] = total_received
            info["fileStats"][0]["bytesCompleted"] = total_received
            info["secondsDownloading"] = int(now - info["_start_time"])

            elapsed = now - last_speed_time
            if elapsed >= 2:
                info["rateDownload"] = int((total_received - last_speed_received) / elapsed)
                last_speed_received = total_received
                last_speed_time = now

            speed = info.get("rateDownload", 0)
            remaining = file_size - total_received
            info["eta"] = int(remaining / speed) if speed > 0 and remaining > 0 else -1

            if now - last_save_time > 5:
                last_save_time = now
                save_state()

            if ws_clients and now - last_broadcast_time >= 1:
                last_broadcast_time = now
                asyncio.create_task(broadcast_downloads())

        chunk_offset = downloaded // STREAM_CHUNK_SIZE
        logger.info(
            "Downloading %s (%.1f MB) via Pyrogram stream_media, offset chunk %d",
            filename, file_size / 1048576, chunk_offset,
        )

        open_mode = "r+b" if downloaded > 0 else "wb"
        with open(tmp_path, open_mode) as f:
            if downloaded > 0:
                f.seek(downloaded)
            async for chunk in client.stream_media(message, offset=chunk_offset):
                f.write(chunk)
                downloaded += len(chunk)
                _update_progress(downloaded)

        os.rename(tmp_path, dest_path)

        # Mark completed
        info["status"] = 6  # TR_STATUS_SEED
        info["percentDone"] = 1.0
        info["leftUntilDone"] = 0
        info["downloadedEver"] = file_size
        info["doneDate"] = int(time.time())
        info["isFinished"] = True
        info["rateDownload"] = 0
        info["eta"] = -1
        info["files"][0]["bytesCompleted"] = file_size
        info["fileStats"][0]["bytesCompleted"] = file_size
        logger.info("Download complete: %s (%.1f MB)", filename, file_size / 1048576)
        await broadcast_downloads()

    except asyncio.CancelledError:
        logger.info("Download #%d cancelled (paused)", torrent_id)
        info["status"] = 0  # TR_STATUS_STOPPED
        info["rateDownload"] = 0
    except Exception as e:
        logger.error("Download failed for torrent #%d: %s", torrent_id, e)
        info["error"] = 1
        info["errorString"] = str(e)
        info["status"] = 0
        info["rateDownload"] = 0
    finally:
        _active_tasks.pop(torrent_id, None)
        save_state()
        await broadcast_downloads()


async def resume_downloads():
    """Resume incomplete downloads after server restart."""
    load_state()
    downloads = get_downloads()
    for tid, info in list(downloads.items()):
        status = info.get("status", 0)
        if status in (3, 4) and not info.get("isFinished", False):
            info["rateDownload"] = 0
            logger.info("Resuming download #%d: %s", tid, info.get("name", "?"))
            enqueue_download(tid)
