import base64
import logging
import os
import time
import uuid

from app.config import settings
from app.download import _bdecode
from app.transmission.state import get_downloads, get_next_id, save_state
from app.transmission.downloader import enqueue_download, get_active_tasks
from app.transmission.websocket import broadcast_downloads

logger = logging.getLogger(__name__)


async def session_get(args):
    return {
        "version": "4.0.0 (telegram-torznab)",
        "rpc-version": 17,
        "rpc-version-minimum": 14,
        "download-dir": settings.DOWNLOAD_DIR,
        "download-dir-free-space": 50_000_000_000,
    }


async def session_stats(args):
    downloads = get_downloads()
    active = sum(1 for d in downloads.values() if d["status"] in (3, 4))
    return {
        "activeTorrentCount": active,
        "pausedTorrentCount": sum(1 for d in downloads.values() if d["status"] == 0),
        "torrentCount": len(downloads),
        "downloadSpeed": sum(d.get("rateDownload", 0) for d in downloads.values()),
        "uploadSpeed": 0,
    }


async def torrent_add(args):
    downloads = get_downloads()

    metainfo_b64 = args.get("metainfo", "")
    download_dir = settings.DOWNLOAD_DIR
    logger.info("torrent-add args: download-dir=%r", download_dir)

    if not metainfo_b64:
        return {"torrent-duplicate": None}

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

    # Check for duplicate
    for existing in downloads.values():
        if existing["chat_id"] == chat_id and existing["msg_id"] == msg_id:
            return {
                "torrent-duplicate": {
                    "id": existing["id"],
                    "hashString": existing["hashString"],
                    "name": existing["name"],
                },
            }

    torrent_id = get_next_id()
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

    downloads[torrent_id] = download_info
    save_state()
    logger.info("Queued download #%d: %s (%s:%d)", torrent_id, name, chat_id, msg_id)

    enqueue_download(torrent_id)
    await broadcast_downloads()

    return {
        "torrent-added": {
            "id": torrent_id,
            "hashString": torrent_hash,
            "name": name,
        },
    }


async def torrent_get(args):
    downloads = get_downloads()
    fields = args.get("fields", [])
    ids = args.get("ids")

    if ids is None:
        torrents = list(downloads.values())
    elif isinstance(ids, list):
        torrents = [downloads[tid] for tid in ids if tid in downloads]
    elif isinstance(ids, int):
        torrents = [downloads[ids]] if ids in downloads else []
    else:
        torrents = list(downloads.values())

    if fields:
        result = []
        for t in torrents:
            filtered = {}
            for f in fields:
                if f in t:
                    filtered[f] = t[f]
            result.append(filtered)
        return {"torrents": result}

    return {
        "torrents": [
            {k: v for k, v in t.items() if not k.startswith("_")}
            for t in torrents
        ],
    }


async def torrent_remove(args):
    downloads = get_downloads()
    active_tasks = get_active_tasks()
    ids = args.get("ids", [])
    delete_local_data = args.get("delete-local-data", False)

    if isinstance(ids, int):
        ids = [ids]

    for tid in ids:
        task = active_tasks.pop(tid, None)
        if task and not task.done():
            task.cancel()
        info = downloads.pop(tid, None)
        if info and delete_local_data:
            path = os.path.join(info["downloadDir"], info["name"])
            if os.path.exists(path):
                os.remove(path)
                logger.info("Deleted: %s", path)

    save_state()
    await broadcast_downloads()
    return {}


async def torrent_stop(args):
    """Pause downloads."""
    downloads = get_downloads()
    active_tasks = get_active_tasks()
    ids = args.get("ids", [])
    if isinstance(ids, int):
        ids = [ids]

    for tid in ids:
        info = downloads.get(tid)
        if not info:
            continue
        task = active_tasks.pop(tid, None)
        if task and not task.done():
            task.cancel()
        info["status"] = 0  # TR_STATUS_STOPPED
        info["rateDownload"] = 0

    save_state()
    await broadcast_downloads()
    return {}


async def torrent_start(args):
    """Resume stopped downloads."""
    downloads = get_downloads()
    active_tasks = get_active_tasks()
    ids = args.get("ids", [])
    if isinstance(ids, int):
        ids = [ids]

    for tid in ids:
        info = downloads.get(tid)
        if not info:
            continue
        if info.get("isFinished", False):
            continue
        if tid in active_tasks and not active_tasks[tid].done():
            continue
        info["error"] = 0
        info["errorString"] = ""
        info["rateDownload"] = 0
        logger.info("Resuming download #%d: %s", tid, info.get("name", "?"))
        enqueue_download(tid)

    save_state()
    await broadcast_downloads()
    return {}


async def torrent_set(args):
    return {}
