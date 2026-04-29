"""REST JSON API v2 — clean endpoints for the mobile/desktop app.

No Torznab XML, no Transmission RPC emulation.
"""

import hmac
import json
import logging
import os
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.channels import get_all_channels, get_channel_by_category
from app.config import settings
from app.media import extract_media_info
from app.telegram_client import get_client
from app.torznab.search import search_channels
from app.transmission.downloader import enqueue_download, get_active_tasks
from app.transmission.state import (
    get_downloads,
    get_downloads_snapshot,
    get_next_id,
    save_state,
)
from app.transmission.websocket import broadcast_downloads, get_ws_clients

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["v2"])


# ── Auth ──────────────────────────────────────────────────────────────────

def _verify_apikey(apikey: str = Query(..., alias="apikey")):
    if not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return apikey


# ── Health ────────────────────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {"status": "ok"}


# ── Channels ──────────────────────────────────────────────────────────────

@router.get("/channels")
async def list_channels(apikey: str = Depends(_verify_apikey)):
    """Return all Telegram channels as JSON."""
    channels = get_all_channels()
    return [
        {
            "id": ch["category_id"],
            "chatId": ch["chat_id"],
            "name": ch["name"],
            "username": ch.get("username"),
        }
        for ch in channels
    ]


# ── Search ────────────────────────────────────────────────────────────────

@router.get("/search")
async def search(
    apikey: str = Depends(_verify_apikey),
    q: str = Query("", description="Search query"),
    channels: str | None = Query(None, description="Channel IDs (comma-separated category IDs)"),
    season: str | None = Query(None),
    ep: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Search Telegram channels and return JSON results."""
    if channels:
        try:
            cat_ids = [int(c.strip()) for c in channels.split(",") if c.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid channel IDs")
        target_channels = [
            ch for cid in cat_ids
            if (ch := get_channel_by_category(cid)) is not None
        ] or get_all_channels()
    else:
        target_channels = get_all_channels()

    all_items = await search_channels(target_channels, q or "", limit, season, ep)
    total = len(all_items)
    paginated = all_items[offset:offset + limit]

    return {
        "total": total,
        "offset": offset,
        "items": [
            {
                "title": item["title"],
                "guid": item["guid"],
                "link": item["link"],
                "pubDate": item["pub_date"].isoformat() if item["pub_date"] else None,
                "size": item["size"],
                "categoryId": item["category_id"],
                "description": item["description"],
            }
            for item in paginated
        ],
    }


# ── Downloads ─────────────────────────────────────────────────────────────

@router.get("/downloads")
async def list_downloads(apikey: str = Depends(_verify_apikey)):
    """Return all downloads as JSON."""
    return get_downloads_snapshot()


@router.get("/stats")
async def stats(apikey: str = Depends(_verify_apikey)):
    """Return session-level download stats."""
    downloads = get_downloads()
    active = sum(1 for d in downloads.values() if d["status"] in (3, 4))
    return {
        "activeTorrentCount": active,
        "pausedTorrentCount": sum(1 for d in downloads.values() if d["status"] == 0),
        "torrentCount": len(downloads),
        "downloadSpeed": sum(d.get("rateDownload", 0) for d in downloads.values()),
    }


@router.post("/downloads")
async def add_download(
    apikey: str = Depends(_verify_apikey),
    chat_id: str = Query(..., alias="chat_id"),
    msg_id: int = Query(..., alias="msg_id"),
):
    """Start a download from Telegram given chat_id and msg_id."""
    downloads = get_downloads()

    # Check for duplicate
    for existing in downloads.values():
        if existing["chat_id"] == chat_id and existing["msg_id"] == msg_id:
            return {"status": "duplicate", "download": {
                "id": existing["id"],
                "name": existing["name"],
            }}

    # Fetch message metadata to get filename and size
    client = get_client()
    try:
        message = await client.get_messages(int(chat_id), msg_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot fetch message: {e}")

    media_info = extract_media_info(message)
    if not media_info:
        raise HTTPException(status_code=400, detail="Message has no downloadable media")

    filename = media_info["filename"] or "unknown"
    file_size = media_info["size"]

    torrent_id = get_next_id()
    torrent_hash = uuid.uuid4().hex[:40]

    download_info = {
        "id": torrent_id,
        "hashString": torrent_hash,
        "name": filename,
        "chat_id": chat_id,
        "msg_id": msg_id,
        "totalSize": file_size,
        "percentDone": 0.0,
        "leftUntilDone": file_size,
        "downloadedEver": 0,
        "uploadedEver": 0,
        "status": 4,
        "rateDownload": 0,
        "rateUpload": 0,
        "eta": -1,
        "error": 0,
        "errorString": "",
        "downloadDir": settings.DOWNLOAD_DIR,
        "addedDate": int(time.time()),
        "doneDate": 0,
        "isFinished": False,
        "secondsDownloading": 0,
        "secondsSeeding": 0,
        "seedRatioLimit": 0,
        "seedRatioMode": 0,
        "files": [{"name": filename, "length": file_size, "bytesCompleted": 0}],
        "fileStats": [{"wanted": True, "priority": 0, "bytesCompleted": 0}],
        "_start_time": time.time(),
    }

    downloads[torrent_id] = download_info
    save_state()

    enqueue_download(torrent_id)
    await broadcast_downloads()

    return {"status": "added", "download": {"id": torrent_id, "name": filename}}


@router.delete("/downloads/{download_id}")
async def remove_download(
    download_id: int,
    apikey: str = Depends(_verify_apikey),
    delete_file: bool = Query(False),
):
    """Remove a download, optionally deleting the file."""
    downloads = get_downloads()
    active_tasks = get_active_tasks()

    task = active_tasks.pop(download_id, None)
    if task and not task.done():
        task.cancel()

    info = downloads.pop(download_id, None)
    if not info:
        raise HTTPException(status_code=404, detail="Download not found")

    if delete_file:
        path = os.path.join(info["downloadDir"], info["name"])
        if os.path.exists(path):
            os.remove(path)

    save_state()
    await broadcast_downloads()
    return {"status": "removed"}


@router.post("/downloads/{download_id}/pause")
async def pause_download(
    download_id: int,
    apikey: str = Depends(_verify_apikey),
):
    """Pause an active download."""
    downloads = get_downloads()
    active_tasks = get_active_tasks()

    info = downloads.get(download_id)
    if not info:
        raise HTTPException(status_code=404, detail="Download not found")

    task = active_tasks.pop(download_id, None)
    if task and not task.done():
        task.cancel()

    info["status"] = 0
    info["rateDownload"] = 0
    save_state()
    await broadcast_downloads()
    return {"status": "paused"}


@router.post("/downloads/{download_id}/resume")
async def resume_download(
    download_id: int,
    apikey: str = Depends(_verify_apikey),
):
    """Resume a paused/failed download."""
    downloads = get_downloads()
    active_tasks = get_active_tasks()

    info = downloads.get(download_id)
    if not info:
        raise HTTPException(status_code=404, detail="Download not found")

    if info.get("isFinished"):
        raise HTTPException(status_code=400, detail="Download already finished")

    if download_id in active_tasks and not active_tasks[download_id].done():
        return {"status": "already_running"}

    info["error"] = 0
    info["errorString"] = ""
    info["rateDownload"] = 0
    enqueue_download(download_id)

    save_state()
    await broadcast_downloads()
    return {"status": "resumed"}


@router.get("/downloads/{download_id}/file")
async def download_file(
    download_id: int,
    apikey: str = Depends(_verify_apikey),
):
    """Serve a completed download file."""
    downloads = get_downloads()
    info = downloads.get(download_id)
    if not info:
        raise HTTPException(status_code=404, detail="Download not found")

    if not info.get("isFinished"):
        raise HTTPException(status_code=400, detail="Download not complete")

    file_path = os.path.join(info["downloadDir"], info["name"])
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(path=file_path, filename=info["name"], media_type="application/octet-stream")


# ── WebSocket ─────────────────────────────────────────────────────────────

@router.websocket("/ws/downloads")
async def ws_downloads(ws: WebSocket, apikey: str = ""):
    """WebSocket for live download progress updates."""
    if not apikey or not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
        await ws.close(code=4001, reason="unauthorized")
        return

    await ws.accept()
    clients = get_ws_clients()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps({
            "type": "downloads",
            "downloads": get_downloads_snapshot(),
        }))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
