import hmac
import logging
import os
import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.config import settings
from app.media import extract_media_info
from app.telegram_client import get_client
from app.torznab.errors import torznab_error
from app.transmission.state import find_by_chat_msg

logger = logging.getLogger(__name__)
router = APIRouter()

CHUNK_SIZE = 1024 * 1024  # 1MB


def _find_cached_file(chat_id: str, msg_id: str) -> str | None:
    """Find a cached file matching chat_id and msg_id.

    Resolution priority:
    1. If download state has a matching entry with ``file_path`` → return it
    2. If download state has a matching entry with ``downloadDir`` → join with name
    3. Fallback: scan ``settings.DOWNLOAD_DIR`` for ``{chat_id}_{msg_id}_*`` prefix
    """
    msg_id_int = int(msg_id)
    entry = find_by_chat_msg(chat_id, msg_id_int)
    if entry:
        # Priority 1: explicit file_path
        fp = entry.get("file_path")
        if fp and os.path.exists(fp):
            return fp

        # Priority 2: downloadDir + name
        dd = entry.get("downloadDir")
        name = entry.get("name")
        if dd and name:
            candidate = os.path.join(dd, name)
            if os.path.exists(candidate):
                return candidate

    # Priority 3: scan DOWNLOAD_DIR (legacy behavior)
    prefix = f"{chat_id}_{msg_id}_"
    if not os.path.isdir(settings.DOWNLOAD_DIR):
        return None
    for fname in os.listdir(settings.DOWNLOAD_DIR):
        if fname.startswith(prefix):
            return os.path.join(settings.DOWNLOAD_DIR, fname)
    return None


@router.get("/api/stream")
async def stream_file(
    request: Request,
    id: str = Query(..., description="chat_id:msg_id"),
    apikey: str = Query(...),
) -> Response:
    if not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
        return torznab_error(100)

    parts = id.split(":")
    if len(parts) != 2:
        return torznab_error(201, "Invalid id format")

    chat_id, msg_id = parts
    try:
        int(chat_id)
        int(msg_id)
    except ValueError:
        return torznab_error(201, "Invalid id: chat_id and msg_id must be numeric")

    cached = _find_cached_file(chat_id, msg_id)

    # Fallback: download from Telegram if not cached
    if not cached:
        client = get_client()
        try:
            message = await client.get_messages(int(chat_id), int(msg_id))
        except Exception as e:
            logger.error("Stream: failed to get message %s:%s: %s", chat_id, msg_id, e)
            return torznab_error(300, "Message not found")

        info = extract_media_info(message)
        if not info:
            return torznab_error(300, "No downloadable media")

        filename = info["filename"] or f"file_{msg_id}"

        safe_name = filename.replace("/", "_").replace("\\", "_")
        cached = os.path.join(settings.DOWNLOAD_DIR, f"{chat_id}_{msg_id}_{safe_name}")
        os.makedirs(settings.DOWNLOAD_DIR, exist_ok=True)
        logger.info("Stream fallback: downloading %s from Telegram", filename)
        await client.download_media(message, file_name=cached)

    file_size = os.path.getsize(cached)
    filename = os.path.basename(cached).split("_", 2)[-1]  # Remove chat_id_msg_id_ prefix

    # Handle Range requests for webseed compatibility
    range_header = request.headers.get("range")
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else file_size - 1
            end = min(end, file_size - 1)
            length = end - start + 1

            async def range_gen():
                with open(cached, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            return StreamingResponse(
                range_gen(),
                status_code=206,
                media_type="application/octet-stream",
                headers={
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(length),
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )

    return FileResponse(
        cached,
        filename=filename,
        media_type="application/octet-stream",
        headers={"Accept-Ranges": "bytes"},
    )
