import asyncio
import json

from fastapi import WebSocket

from app.transmission.state import get_downloads_snapshot

_ws_clients: set[WebSocket] = set()


def get_ws_clients() -> set[WebSocket]:
    return _ws_clients


_BROADCAST_TIMEOUT = 5  # seconds


async def broadcast_downloads():
    """Send current download state to all connected WebSocket clients.

    Each client has a ``_BROADCAST_TIMEOUT`` deadline. Stale or half-open
    connections that do not drain within that window are removed.
    """
    if not _ws_clients:
        return
    data = json.dumps({"type": "downloads", "downloads": get_downloads_snapshot()})
    dead = set()
    for ws in _ws_clients:
        try:
            await asyncio.wait_for(ws.send_text(data), timeout=_BROADCAST_TIMEOUT)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)
