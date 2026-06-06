"""REST JSON API v2 — clean endpoints for the mobile/desktop app.

No Torznab XML, no Transmission RPC emulation.
"""

import hmac
import json
import logging
import os
import shutil
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.channels import get_all_channels, get_channel_by_category, get_category_by_chat
from app.config import settings
from app.destinations import DestinationsManager, list_dir
from app.media import extract_media_info
from app.telegram_client import get_channel_info, get_channel_messages, get_client, get_message_thumbnail
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

def _verify_apikey(apikey: str = Query("", alias="apikey")):
    if not apikey or not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
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


def _known_channel(chat_id: int) -> dict:
    channel = get_category_by_chat(str(chat_id))
    if not channel:
        raise HTTPException(status_code=404, detail="Unknown channel")
    return channel


def _telegram_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


@router.get("/channels/{chat_id}")
async def channel_info(chat_id: int, apikey: str = Depends(_verify_apikey)):
    """Return Telegram channel metadata for a known configured channel."""
    _known_channel(chat_id)
    try:
        return await get_channel_info(chat_id)
    except RuntimeError as e:
        raise _telegram_error(502, f"Telegram unavailable: {e}")
    except Exception as e:
        raise _telegram_error(404, f"Channel inaccessible: {e}")


@router.get("/channels/{chat_id}/messages")
async def channel_messages(
    chat_id: int,
    apikey: str = Depends(_verify_apikey),
    before: int | None = Query(None),
    around: int | None = Query(None),
    limit: int = Query(20, ge=1, le=50),
):
    """Return downloadable channel messages with cursor pagination."""
    channel = _known_channel(chat_id)
    try:
        page = await get_channel_messages(chat_id, before=before, around=around, limit=limit)
        metadata = await get_channel_info(chat_id)
    except TimeoutError as e:
        raise _telegram_error(429, str(e) or "Telegram rate limit, retry later")
    except RuntimeError as e:
        raise _telegram_error(502, f"Telegram unavailable: {e}")
    except Exception as e:
        raise _telegram_error(404, f"Channel inaccessible: {e}")

    return {
        **page,
        "channel": metadata or {"id": chat_id, "title": channel["name"]},
    }


@router.get("/channels/{chat_id}/messages/{msg_id}/thumbnail")
async def channel_message_thumbnail(
    chat_id: int,
    msg_id: int,
    apikey: str = Depends(_verify_apikey),
):
    """Return a cached thumbnail for a message without downloading its full media."""
    _known_channel(chat_id)
    try:
        path = await get_message_thumbnail(chat_id, msg_id, os.path.join(settings.DOWNLOAD_DIR, "thumbnails"))
    except RuntimeError as e:
        raise _telegram_error(502, f"Telegram unavailable: {e}")
    except Exception as e:
        raise _telegram_error(404, f"Thumbnail unavailable: {e}")
    if not path:
        raise HTTPException(status_code=404, detail="Thumbnail unavailable")
    return FileResponse(path)


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


# ── Destinations (Folders) ──────────────────────────────────────────────


@router.get("/folders")
async def list_folders(apikey: str = Depends(_verify_apikey)):
    """Return all configured destination folders."""
    mgr = DestinationsManager()
    return [
        {"id": d.id, "name": d.name, "path": d.path, "created_at": d.created_at}
        for d in mgr.list()
    ]


@router.post("/folders", status_code=201)
async def create_folder(
    body: dict,
    apikey: str = Depends(_verify_apikey),
):
    """Create a new destination folder."""
    name = body.get("name", "").strip()
    path = body.get("path", "").strip()
    if not name or not path:
        raise HTTPException(status_code=400, detail="name and path are required")
    mgr = DestinationsManager()
    try:
        dest = mgr.add(name, path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": dest.id, "name": dest.name, "path": dest.path, "created_at": dest.created_at}


@router.delete("/folders/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: str,
    apikey: str = Depends(_verify_apikey),
):
    """Delete a destination folder. Blocked if any active download uses it."""
    mgr = DestinationsManager()
    dest = mgr.get(folder_id)
    if not dest:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Check for active (non-finished) downloads using this destination
    downloads = get_downloads()
    active_using = [
        tid for tid, info in downloads.items()
        if info.get("downloadDir") == dest.path and not info.get("isFinished")
    ]
    if active_using:
        raise HTTPException(
            status_code=409,
            detail=f"Folder has {len(active_using)} active download(s). Finish or remove them first.",
        )

    mgr.remove(folder_id)


# ── File Browser ────────────────────────────────────────────────────────


@router.get("/browse")
async def browse(
    path: str = Query("/"),
    show_hidden: bool = Query(False),
    apikey: str = Depends(_verify_apikey),
):
    """Browse a directory on the server filesystem."""
    # Reject path traversal
    if ".." in path.split(os.sep):
        raise HTTPException(status_code=403, detail="Path traversal detected")

    result = list_dir(path, show_hidden=show_hidden)
    if "error" in result and not result["entries"]:
        # Permission error, nonexistent path — return 200 with error message
        return result
    return result


# ── Move Downloads ──────────────────────────────────────────────────────


@router.post("/downloads/{download_id}/move")
async def move_download(
    download_id: int,
    body: dict,
    apikey: str = Depends(_verify_apikey),
):
    """Move a download to a destination folder."""
    mgr = DestinationsManager()
    dest_id = body.get("destination_id")
    if not dest_id:
        raise HTTPException(status_code=400, detail="destination_id is required")

    dest = mgr.get(dest_id)
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")

    downloads = get_downloads()
    info = downloads.get(download_id)
    if not info:
        raise HTTPException(status_code=404, detail="Download not found")

    old_dir = info["downloadDir"]
    new_dir = dest.path
    name = info.get("name", "")

    # Update downloadDir always
    info["downloadDir"] = new_dir

    if info.get("isFinished") and name:
        # Move file on disk
        old_path = os.path.join(old_dir, name)
        new_path = os.path.join(new_dir, name)
        if os.path.exists(old_path):
            try:
                os.makedirs(new_dir, exist_ok=True)
                shutil.move(old_path, new_path)
            except (OSError, PermissionError) as e:
                info["downloadDir"] = old_dir
                save_state()
                raise HTTPException(status_code=500, detail=f"Failed to move file: {e}")
        else:
            info["downloadDir"] = old_dir
            save_state()
            raise HTTPException(status_code=500, detail=f"File not found: {old_path}")

    # Set file_path
    if name:
        info["file_path"] = os.path.join(new_dir, name)

    save_state()
    await broadcast_downloads()
    return {"status": "moved"}


@router.post("/downloads/bulk-move")
async def bulk_move_downloads(
    body: dict,
    apikey: str = Depends(_verify_apikey),
):
    """Move multiple downloads to a destination folder."""
    ids: list[int] = body.get("ids", [])
    dest_id = body.get("destination_id")
    if not ids or not dest_id:
        raise HTTPException(status_code=400, detail="ids and destination_id are required")

    mgr = DestinationsManager()
    dest = mgr.get(dest_id)
    if not dest:
        raise HTTPException(status_code=404, detail="Destination not found")

    downloads = get_downloads()
    results: list[dict] = []
    new_dir = dest.path

    for tid in ids:
        info = downloads.get(tid)
        if not info:
            results.append({"id": tid, "status": "error", "error": "Download not found"})
            continue

        name = info.get("name", "")
        old_dir = info["downloadDir"]

        # Update downloadDir always
        info["downloadDir"] = new_dir

        if info.get("isFinished") and name:
            old_path = os.path.join(old_dir, name)
            new_path = os.path.join(new_dir, name)
            if os.path.exists(old_path):
                try:
                    os.makedirs(new_dir, exist_ok=True)
                    shutil.move(old_path, new_path)
                except (OSError, PermissionError) as e:
                    info["downloadDir"] = old_dir
                    results.append({"id": tid, "status": "error", "error": str(e)})
                    continue
            else:
                info["downloadDir"] = old_dir
                results.append({"id": tid, "status": "error", "error": "File not found"})
                continue

        if name:
            info["file_path"] = os.path.join(new_dir, name)
        results.append({"id": tid, "status": "moved"})

    save_state()
    await broadcast_downloads()
    return {"results": results}


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
