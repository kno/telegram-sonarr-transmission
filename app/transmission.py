import asyncio
import base64
import hmac
import json
import logging
import os
import time
import uuid

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.download import _bdecode
from app.telegram_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter()

# Session ID for CSRF protection (Transmission protocol requirement)
SESSION_ID = uuid.uuid4().hex[:48]

# Download manager state
_downloads: dict[int, dict] = {}
_next_id = 1
_active_tasks: dict[int, asyncio.Task] = {}
_download_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None

# WebSocket clients for live progress updates
_ws_clients: set[WebSocket] = set()


def _get_downloads_snapshot() -> list[dict]:
    """Return serializable snapshot of all downloads for WebSocket broadcast."""
    return [
        {k: v for k, v in t.items() if not k.startswith("_")}
        for t in _downloads.values()
    ]


async def _broadcast_downloads():
    """Send current download state to all connected WebSocket clients."""
    if not _ws_clients:
        return
    data = json.dumps({"type": "downloads", "downloads": _get_downloads_snapshot()})
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)


async def _queue_worker():
    """Process downloads one at a time from the queue."""
    while True:
        torrent_id = await _download_queue.get()
        info = _downloads.get(torrent_id)
        if not info or info.get("isFinished") or info.get("status") == 0:
            _download_queue.task_done()
            continue

        info["status"] = 4  # TR_STATUS_DOWNLOAD
        info["_start_time"] = time.time()
        _save_state()

        task = asyncio.create_task(_download_from_telegram(torrent_id))
        _active_tasks[torrent_id] = task
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            # The download task was cancelled (paused), but the worker continues
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


def _enqueue_download(torrent_id: int):
    """Add a download to the queue."""
    _ensure_queue()
    info = _downloads.get(torrent_id)
    if info:
        info["status"] = 3  # TR_STATUS_CHECK_WAIT (queued)
        _save_state()
    _download_queue.put_nowait(torrent_id)

# --- Persistence ---

def _state_file() -> str:
    return os.path.join(settings.SESSION_DIR, "downloads.json")


def _save_state():
    """Persist download state to disk."""
    serializable = {}
    for tid, info in _downloads.items():
        entry = {k: v for k, v in info.items() if not k.startswith("_")}
        serializable[str(tid)] = entry
    try:
        path = _state_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w") as f:
            json.dump(serializable, f)
        os.replace(path + ".tmp", path)
    except Exception as e:
        logger.error("Failed to save download state: %s", e)


def _load_state():
    """Restore download state from disk."""
    global _next_id
    path = _state_file()
    if not os.path.exists(path):
        return
    try:
        with open(path) as f:
            data = json.load(f)
        for tid_str, info in data.items():
            tid = int(tid_str)
            info["id"] = tid
            _downloads[tid] = info
            if tid >= _next_id:
                _next_id = tid + 1
        logger.info("Restored %d download(s) from state file", len(_downloads))
    except Exception as e:
        logger.error("Failed to load download state: %s", e)


async def resume_downloads():
    """Resume incomplete downloads after server restart."""
    _load_state()
    for tid, info in list(_downloads.items()):
        status = info.get("status", 0)
        # Resume downloads that were active (downloading or queued)
        if status in (3, 4) and not info.get("isFinished", False):
            info["rateDownload"] = 0
            logger.info("Resuming download #%d: %s", tid, info.get("name", "?"))
            _enqueue_download(tid)


def _check_auth(request: Request):
    """Verify HTTP Basic Auth. Return error response if invalid."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            username, password = decoded.split(":", 1)
            # Accept any username with the correct API key as password
            if password != settings.TORZNAB_APIKEY:
                return JSONResponse(status_code=401, content={"result": "unauthorized"})
        except Exception:
            return JSONResponse(status_code=401, content={"result": "unauthorized"})
    # Also accept requests without auth (for direct testing)
    return None


def _check_session(request: Request):
    """Verify X-Transmission-Session-Id header. Return error response if invalid."""
    client_session = request.headers.get("X-Transmission-Session-Id", "")
    if client_session != SESSION_ID:
        return JSONResponse(
            status_code=409,
            headers={"X-Transmission-Session-Id": SESSION_ID},
            content={"result": "error"},
        )
    return None


def _rpc_response(result: str, arguments: dict, tag=None):
    resp = {"result": result, "arguments": arguments}
    if tag is not None:
        resp["tag"] = tag
    return JSONResponse(
        content=resp,
        headers={"X-Transmission-Session-Id": SESSION_ID},
    )


@router.get("/transmission/rpc")
async def transmission_rpc_get(request: Request):
    """Handle GET requests — Sonarr uses this to verify the endpoint exists."""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err
    return JSONResponse(
        status_code=409,
        headers={"X-Transmission-Session-Id": SESSION_ID},
        content={"result": "error"},
    )


@router.post("/transmission/rpc")
async def transmission_rpc(request: Request):
    # Auth check
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    # CSRF check
    err = _check_session(request)
    if err:
        return err

    body = await request.json()
    method = body.get("method", "")
    arguments = body.get("arguments", {})
    tag = body.get("tag")

    handlers = {
        "session-get": _session_get,
        "session-stats": _session_stats,
        "torrent-add": _torrent_add,
        "torrent-get": _torrent_get,
        "torrent-remove": _torrent_remove,
        "torrent-set": _torrent_set,
        "torrent-start": _torrent_start,
        "torrent-stop": _torrent_stop,
    }

    handler = handlers.get(method)
    if handler is None:
        return _rpc_response("method not recognized", {}, tag)

    result_args = await handler(arguments)
    return _rpc_response("success", result_args, tag)


async def _session_get(args):
    return {
        "version": "4.0.0 (telegram-torznab)",
        "rpc-version": 17,
        "rpc-version-minimum": 14,
        "download-dir": settings.DOWNLOAD_DIR,
        "download-dir-free-space": 50_000_000_000,
    }


async def _session_stats(args):
    active = sum(1 for d in _downloads.values() if d["status"] in (3, 4))
    return {
        "activeTorrentCount": active,
        "pausedTorrentCount": sum(1 for d in _downloads.values() if d["status"] == 0),
        "torrentCount": len(_downloads),
        "downloadSpeed": sum(d.get("rateDownload", 0) for d in _downloads.values()),
        "uploadSpeed": 0,
    }


async def _torrent_add(args):
    global _next_id

    metainfo_b64 = args.get("metainfo", "")
    download_dir = args.get("download-dir", settings.DOWNLOAD_DIR)
    logger.info("torrent-add args: download-dir=%r", download_dir)

    if not metainfo_b64:
        return {"torrent-duplicate": None}

    # Decode .torrent and extract our metadata from the comment field
    try:
        torrent_data = base64.b64decode(metainfo_b64)
        torrent_dict = _bdecode(torrent_data)
    except Exception as e:
        logger.error("Failed to decode torrent: %s", e)
        return {"torrent-duplicate": None}

    comment = torrent_dict.get(b"comment", b"").decode()
    info = torrent_dict.get(b"info", {})
    name = info.get(b"name", b"unknown").decode()
    size = info.get(b"length", 0)

    if ":" not in comment:
        logger.error("Torrent comment missing chat_id:msg_id: %s", comment)
        return {"torrent-duplicate": None}

    chat_id, msg_id_str = comment.rsplit(":", 1)
    try:
        msg_id = int(msg_id_str)
    except ValueError:
        return {"torrent-duplicate": None}

    # Check for duplicate (same chat_id:msg_id already downloading)
    for existing in _downloads.values():
        if existing["chat_id"] == chat_id and existing["msg_id"] == msg_id:
            return {
                "torrent-duplicate": {
                    "id": existing["id"],
                    "hashString": existing["hashString"],
                    "name": existing["name"],
                },
            }

    torrent_id = _next_id
    _next_id += 1
    torrent_hash = uuid.uuid4().hex[:40]

    download_info = {
        "id": torrent_id,
        "hashString": torrent_hash,
        "name": name,
        "chat_id": chat_id,
        "msg_id": msg_id,
        "totalSize": size,
        "percentDone": 0.0,
        "leftUntilDone": size,
        "downloadedEver": 0,
        "uploadedEver": 0,
        "status": 4,  # TR_STATUS_DOWNLOAD
        "rateDownload": 0,
        "rateUpload": 0,
        "eta": -1,
        "error": 0,
        "errorString": "",
        "downloadDir": download_dir,
        "addedDate": int(time.time()),
        "doneDate": 0,
        "isFinished": False,
        "secondsDownloading": 0,
        "secondsSeeding": 0,
        "seedRatioLimit": 0,
        "seedRatioMode": 0,
        "files": [{"name": name, "length": size, "bytesCompleted": 0}],
        "fileStats": [{"wanted": True, "priority": 0, "bytesCompleted": 0}],
        "_start_time": time.time(),
    }

    _downloads[torrent_id] = download_info
    _save_state()
    logger.info("Queued download #%d: %s (%s:%d)", torrent_id, name, chat_id, msg_id)

    _enqueue_download(torrent_id)
    await _broadcast_downloads()

    return {
        "torrent-added": {
            "id": torrent_id,
            "hashString": torrent_hash,
            "name": name,
        },
    }


STREAM_CHUNK_SIZE = 1024 * 1024  # 1MB — Pyrogram's stream_media chunk size


async def _download_from_telegram(torrent_id: int):
    info = _downloads.get(torrent_id)
    if not info:
        return

    try:
        client = get_client()
        message = await client.get_messages(int(info["chat_id"]), info["msg_id"])

        if not message or not message.document:
            info["error"] = 1
            info["errorString"] = "No media in message"
            info["status"] = 0
            _save_state()
            return

        doc = message.document
        filename = doc.file_name or info["name"]
        file_size = doc.file_size or 0

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
            # Align to chunk boundary (stream_media works in 1MB chunks)
            aligned = (tmp_size // STREAM_CHUNK_SIZE) * STREAM_CHUNK_SIZE
            if aligned > 0 and aligned < file_size:
                downloaded = aligned
                # Truncate to aligned boundary in case last chunk was partial
                with open(tmp_path, "r+b") as f:
                    f.truncate(downloaded)
                logger.info(
                    "Resuming download at %.1f MB / %.1f MB: %s",
                    downloaded / 1048576, file_size / 1048576, filename,
                )
            else:
                # File is empty, corrupted, or oversized — start fresh
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
                _save_state()

            # Broadcast progress via WebSocket every 1s
            if _ws_clients and now - last_broadcast_time >= 1:
                last_broadcast_time = now
                asyncio.create_task(_broadcast_downloads())

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
        await _broadcast_downloads()

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
        _save_state()
        await _broadcast_downloads()


async def _torrent_get(args):
    fields = args.get("fields", [])
    ids = args.get("ids")

    if ids is None:
        torrents = list(_downloads.values())
    elif isinstance(ids, list):
        torrents = [_downloads[tid] for tid in ids if tid in _downloads]
    elif isinstance(ids, int):
        torrents = [_downloads[ids]] if ids in _downloads else []
    else:
        torrents = list(_downloads.values())

    if fields:
        # Return only requested fields (exclude internal fields starting with _)
        result = []
        for t in torrents:
            filtered = {}
            for f in fields:
                if f in t:
                    filtered[f] = t[f]
            result.append(filtered)
        return {"torrents": result}

    # Return all fields except internal ones
    return {
        "torrents": [
            {k: v for k, v in t.items() if not k.startswith("_")}
            for t in torrents
        ],
    }


async def _torrent_remove(args):
    ids = args.get("ids", [])
    delete_local_data = args.get("delete-local-data", False)

    if isinstance(ids, int):
        ids = [ids]

    for tid in ids:
        # Cancel active download task
        task = _active_tasks.pop(tid, None)
        if task and not task.done():
            task.cancel()
        info = _downloads.pop(tid, None)
        if info and delete_local_data:
            path = os.path.join(info["downloadDir"], info["name"])
            if os.path.exists(path):
                os.remove(path)
                logger.info("Deleted: %s", path)

    _save_state()
    await _broadcast_downloads()
    return {}


async def _torrent_stop(args):
    """Pause downloads."""
    ids = args.get("ids", [])
    if isinstance(ids, int):
        ids = [ids]

    for tid in ids:
        info = _downloads.get(tid)
        if not info:
            continue
        # Cancel active download task
        task = _active_tasks.pop(tid, None)
        if task and not task.done():
            task.cancel()
        info["status"] = 0  # TR_STATUS_STOPPED
        info["rateDownload"] = 0

    _save_state()
    await _broadcast_downloads()
    return {}


async def _torrent_start(args):
    """Resume stopped downloads."""
    ids = args.get("ids", [])
    if isinstance(ids, int):
        ids = [ids]

    for tid in ids:
        info = _downloads.get(tid)
        if not info:
            continue
        # Only resume if stopped and not finished
        if info.get("isFinished", False):
            continue
        if tid in _active_tasks and not _active_tasks[tid].done():
            continue  # Already running
        info["error"] = 0
        info["errorString"] = ""
        info["rateDownload"] = 0
        logger.info("Resuming download #%d: %s", tid, info.get("name", "?"))
        _enqueue_download(tid)

    _save_state()
    await _broadcast_downloads()
    return {}


async def _torrent_set(args):
    # Accept but ignore — Sonarr sometimes sets labels, speed limits, etc.
    return {}


@router.get("/transmission/files/{torrent_id}")
async def serve_download(torrent_id: int, request: Request, apikey: str = ""):
    """Serve a completed download file to the browser."""
    # Accept apikey as query param (for browser downloads) or Basic Auth header
    if apikey:
        if not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
    else:
        auth_err = _check_auth(request)
        if auth_err:
            return auth_err

    info = _downloads.get(torrent_id)
    if not info:
        return JSONResponse(status_code=404, content={"error": "not found"})

    if not info.get("isFinished", False):
        return JSONResponse(status_code=400, content={"error": "download not complete"})

    file_path = os.path.join(info["downloadDir"], info["name"])
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "file not found on disk"})

    return FileResponse(
        path=file_path,
        filename=info["name"],
        media_type="application/octet-stream",
    )


@router.websocket("/ws/downloads")
async def ws_downloads(ws: WebSocket, apikey: str = ""):
    """WebSocket endpoint for live download progress updates."""
    if not apikey or not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
        await ws.close(code=4001, reason="unauthorized")
        return
    await ws.accept()
    _ws_clients.add(ws)
    try:
        # Send initial state
        await ws.send_text(json.dumps({
            "type": "downloads",
            "downloads": _get_downloads_snapshot(),
        }))
        # Keep connection alive, listen for close
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
