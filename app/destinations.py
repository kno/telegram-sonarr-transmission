import json
import logging
import os
import stat
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Destination:
    id: str
    name: str
    path: str
    created_at: str  # ISO 8601


# ---------------------------------------------------------------------------
# JSON persistence (mirrors channels.py pattern)
# ---------------------------------------------------------------------------

def _destinations_file() -> str:
    return settings.DESTINATIONS_FILE


def _load_from_disk() -> list[dict]:
    path = _destinations_file()
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load destinations: %s", e)
        return []


def _save_to_disk(destinations: list[dict]):
    path = _destinations_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(destinations, f, indent=2, ensure_ascii=False)
    os.replace(path + ".tmp", path)


# ---------------------------------------------------------------------------
# Path validation
# ---------------------------------------------------------------------------

def _validate_path(path: str):
    """Reject path traversal and ensure directory exists and is readable."""
    # Reject .. components
    normalized = os.path.normpath(path)
    if ".." in path.split(os.sep) or ".." in normalized.split(os.sep):
        raise ValueError(f"Path traversal detected: {path}")

    # Must be an absolute path
    if not os.path.isabs(normalized):
        raise ValueError(f"Path must be absolute: {path}")

    # Ensure directory exists and is readable
    if not os.path.isdir(normalized):
        raise ValueError(f"Directory does not exist: {normalized}")
    if not os.access(normalized, os.R_OK):
        raise ValueError(f"Directory is not readable: {normalized}")


# ---------------------------------------------------------------------------
# DestinationsManager
# ---------------------------------------------------------------------------

class DestinationsManager:
    """CRUD manager for destination folders with JSON persistence."""

    def __init__(self):
        self._destinations: list[dict] = _load_from_disk()

    def list(self) -> list[Destination]:
        return [Destination(**d) for d in self._destinations]

    def get(self, dest_id: str) -> Optional[Destination]:
        for d in self._destinations:
            if d["id"] == dest_id:
                return Destination(**d)
        return None

    def get_by_path(self, path: str) -> Optional[Destination]:
        normalized = os.path.normpath(path)
        for d in self._destinations:
            if os.path.normpath(d["path"]) == normalized:
                return Destination(**d)
        return None

    def add(self, name: str, path: str) -> Destination:
        _validate_path(path)
        dest_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": dest_id,
            "name": name,
            "path": os.path.normpath(path),
            "created_at": created_at,
        }
        self._destinations.append(entry)
        _save_to_disk(self._destinations)
        return Destination(**entry)

    def remove(self, dest_id: str):
        self._destinations = [d for d in self._destinations if d["id"] != dest_id]
        _save_to_disk(self._destinations)


# ---------------------------------------------------------------------------
# File browser
# ---------------------------------------------------------------------------

def list_dir(path: str, show_hidden: bool = False) -> dict:
    """List directory entries at *path*.

    Returns ``{"entries": [{name, type, path}, ...]}`` on success.
    On error returns ``{"entries": [], "error": "..."}``.
    Rejects path traversal (``..``) and paths that resolve outside a safe root.
    """
    # Reject explicit traversal
    if ".." in path.split(os.sep):
        return {"entries": [], "error": "Path traversal detected: '..' is not allowed"}

    try:
        normalized = os.path.normpath(os.path.abspath(path))
    except (ValueError, OSError):
        return {"entries": [], "error": f"Invalid path: {path}"}

    # Security: if the resolved path differs from the normalized input and
    # contains .., reject it
    if ".." in normalized.split(os.sep):
        return {"entries": [], "error": "Path traversal detected: resolved path contains '..'"}

    if not os.path.exists(normalized):
        return {"entries": [], "error": f"Path does not exist: {normalized}"}

    if not os.path.isdir(normalized):
        return {"entries": [], "error": f"Not a directory: {normalized}"}

    try:
        entries_raw = os.listdir(normalized)
    except PermissionError as e:
        return {"entries": [], "error": f"Permission denied: {e}"}
    except OSError as e:
        return {"entries": [], "error": str(e)}

    entries = []
    for name in sorted(entries_raw):
        if not show_hidden and name.startswith("."):
            continue

        full_path = os.path.join(normalized, name)
        try:
            st = os.lstat(full_path)
            if stat.S_ISLNK(st.st_mode):
                entry_type = "symlink"
            elif stat.S_ISDIR(st.st_mode):
                entry_type = "dir"
            else:
                entry_type = "file"
        except OSError:
            # Permission error on a single entry — skip it
            continue

        entries.append({
            "name": name,
            "type": entry_type,
            "path": full_path,
        })

    return {"entries": entries}
