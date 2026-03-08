import json
import logging
import os

from app.config import settings

logger = logging.getLogger(__name__)

# Download manager state
_downloads: dict[int, dict] = {}
_next_id = 1


def get_downloads() -> dict[int, dict]:
    return _downloads


def get_next_id() -> int:
    global _next_id
    tid = _next_id
    _next_id += 1
    return tid


def get_downloads_snapshot() -> list[dict]:
    """Return serializable snapshot of all downloads for WebSocket broadcast."""
    return [
        {k: v for k, v in t.items() if not k.startswith("_")}
        for t in _downloads.values()
    ]


def _state_file() -> str:
    return os.path.join(settings.SESSION_DIR, "downloads.json")


def save_state():
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


def load_state():
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
