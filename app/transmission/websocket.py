import json

from fastapi import WebSocket

from app.transmission.state import get_downloads_snapshot

_ws_clients: set[WebSocket] = set()


def get_ws_clients() -> set[WebSocket]:
    return _ws_clients


async def broadcast_downloads():
    """Send current download state to all connected WebSocket clients."""
    if not _ws_clients:
        return
    data = json.dumps({"type": "downloads", "downloads": get_downloads_snapshot()})
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _ws_clients.difference_update(dead)
