import hmac
import logging

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.config import settings
from app.telegram_client import get_client
from app.torznab.errors import torznab_error

logger = logging.getLogger(__name__)
router = APIRouter()


def _bencode(obj):
    """Minimal bencoding implementation."""
    if isinstance(obj, int):
        return f"i{obj}e".encode()
    if isinstance(obj, bytes):
        return f"{len(obj)}:".encode() + obj
    if isinstance(obj, str):
        return _bencode(obj.encode())
    if isinstance(obj, list):
        return b"l" + b"".join(_bencode(x) for x in obj) + b"e"
    if isinstance(obj, dict):
        items = sorted(obj.items())
        return b"d" + b"".join(_bencode(k) + _bencode(v) for k, v in items) + b"e"
    raise TypeError(f"Cannot bencode {type(obj)}")


def _bdecode(data: bytes):
    """Minimal bdecoding implementation."""
    def _decode(data, idx):
        ch = data[idx:idx + 1]
        if ch == b"i":
            end = data.index(b"e", idx)
            return int(data[idx + 1:end]), end + 1
        elif ch == b"l":
            lst = []
            idx += 1
            while data[idx:idx + 1] != b"e":
                val, idx = _decode(data, idx)
                lst.append(val)
            return lst, idx + 1
        elif ch == b"d":
            dct = {}
            idx += 1
            while data[idx:idx + 1] != b"e":
                key, idx = _decode(data, idx)
                val, idx = _decode(data, idx)
                dct[key] = val
            return dct, idx + 1
        elif ch.isdigit():
            colon = data.index(b":", idx)
            length = int(data[idx:colon])
            start = colon + 1
            return data[start:start + length], start + length
        raise ValueError(f"Invalid bencode at position {idx}")

    result, _ = _decode(data, 0)
    return result


def create_minimal_torrent(filename: str, size: int, chat_id: str, msg_id: int) -> bytes:
    """Create a minimal .torrent file instantly without downloading the actual content.

    The .torrent contains metadata and a comment with chat_id:msg_id so our
    fake Transmission RPC can extract it and handle the real download.
    """
    # Use a standard piece length and generate correct number of dummy hashes
    piece_length = 524288  # 512 KB
    num_pieces = (size + piece_length - 1) // piece_length if size > 0 else 1
    info = {
        b"length": size,
        b"name": filename.encode("utf-8"),
        b"piece length": piece_length,
        b"pieces": b"\x00" * (20 * num_pieces),
    }

    torrent = {
        b"comment": f"{chat_id}:{msg_id}".encode(),
        b"created by": b"telegram-torznab",
        b"info": info,
    }

    return _bencode(torrent)


@router.get("/api/download")
async def download_torrent(
    id: str = Query(..., description="chat_id:msg_id"),
    apikey: str = Query(...),
) -> Response:
    if not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
        return torznab_error(100)

    parts = id.split(":")
    if len(parts) != 2:
        return torznab_error(201, "Invalid id format. Expected chat_id:msg_id")

    chat_id, msg_id = parts
    try:
        int(chat_id)
        msg_id_int = int(msg_id)
    except ValueError:
        return torznab_error(201, "Invalid id: chat_id and msg_id must be numeric")

    client = get_client()
    try:
        entity = await client.get_entity(int(chat_id))
        message = await client.get_messages(entity, ids=msg_id_int)
    except Exception as e:
        logger.error("Failed to get message %s:%s: %s", chat_id, msg_id, e)
        return torznab_error(300, "Message not found")

    if not message or not message.media:
        return torznab_error(300, "Message has no downloadable media")

    # Extract metadata (fast, no file download)
    doc = message.media.document
    filename = f"file_{message.id}"
    for attr in doc.attributes:
        if hasattr(attr, "file_name"):
            filename = attr.file_name
            break

    size = doc.size or 0

    # Generate minimal .torrent instantly
    torrent_bytes = create_minimal_torrent(filename, size, chat_id, msg_id_int)

    return Response(
        content=torrent_bytes,
        media_type="application/x-bittorrent",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.torrent"',
        },
    )
