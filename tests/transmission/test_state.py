import json
import os

import pytest

from app.transmission.state import (
    get_downloads,
    get_next_id,
    get_downloads_snapshot,
    save_state,
    load_state,
)


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level state for every test."""
    import app.transmission.state as mod
    old_downloads = dict(mod._downloads)
    old_next_id = mod._next_id
    mod._downloads.clear()
    mod._next_id = 1
    yield
    mod._downloads.clear()
    mod._downloads.update(old_downloads)
    mod._next_id = old_next_id


class TestGetDownloads:
    def test_empty(self):
        assert get_downloads() == {}

    def test_returns_same_dict(self):
        d = get_downloads()
        d[1] = {"name": "test"}
        assert get_downloads()[1]["name"] == "test"


class TestGetNextId:
    def test_increments(self):
        assert get_next_id() == 1
        assert get_next_id() == 2
        assert get_next_id() == 3


class TestGetDownloadsSnapshot:
    def test_filters_private_keys(self):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "test", "_start_time": 12345, "_secret": "hidden"}
        snapshot = get_downloads_snapshot()
        assert len(snapshot) == 1
        assert "id" in snapshot[0]
        assert "name" in snapshot[0]
        assert "_start_time" not in snapshot[0]
        assert "_secret" not in snapshot[0]

    def test_empty(self):
        assert get_downloads_snapshot() == []


class TestSaveLoadState:
    def test_save_creates_file(self, test_settings):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "test.mkv", "status": 4}
        save_state()
        state_file = os.path.join(test_settings.SESSION_DIR, "downloads.json")
        assert os.path.exists(state_file)
        with open(state_file) as f:
            data = json.load(f)
        assert "1" in data
        assert data["1"]["name"] == "test.mkv"

    def test_save_filters_private_keys(self, test_settings):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "test", "_start_time": 999}
        save_state()
        state_file = os.path.join(test_settings.SESSION_DIR, "downloads.json")
        with open(state_file) as f:
            data = json.load(f)
        assert "_start_time" not in data["1"]

    def test_save_atomic_no_tmp_left(self, test_settings):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "test"}
        save_state()
        state_file = os.path.join(test_settings.SESSION_DIR, "downloads.json")
        assert not os.path.exists(state_file + ".tmp")
        assert os.path.exists(state_file)

    def test_load_restores(self, test_settings):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "loaded.mkv", "status": 6}
        save_state()
        downloads.clear()
        load_state()
        assert 1 in downloads
        assert downloads[1]["name"] == "loaded.mkv"

    def test_load_updates_next_id(self, test_settings):
        import app.transmission.state as mod
        downloads = get_downloads()
        downloads[5] = {"id": 5, "name": "test"}
        save_state()
        downloads.clear()
        mod._next_id = 1
        load_state()
        assert mod._next_id == 6

    def test_load_file_missing(self, test_settings):
        # Should not raise
        load_state()
        assert get_downloads() == {}

    def test_load_corrupt_json(self, test_settings):
        state_file = os.path.join(test_settings.SESSION_DIR, "downloads.json")
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        with open(state_file, "w") as f:
            f.write("not valid json{{{")
        # Should not raise, just log error
        load_state()
        assert get_downloads() == {}


# ===================================================================
# Task 1.3: find_by_chat_msg
# ===================================================================

class TestFindByChatMsg:
    def test_finds_exact_match(self):
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "test.mkv",
            "chat_id": "-100123", "msg_id": 42,
            "_file_path": "/data/cache/test.mkv",
        }
        downloads[2] = {
            "id": 2, "name": "other.mkv",
            "chat_id": "-100456", "msg_id": 99,
        }
        from app.transmission.state import find_by_chat_msg
        result = find_by_chat_msg("-100123", 42)
        assert result is not None
        assert result["id"] == 1
        assert result["name"] == "test.mkv"
        assert result["_file_path"] == "/data/cache/test.mkv"

    def test_returns_none_for_no_match(self):
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "test.mkv",
            "chat_id": "-100123", "msg_id": 42,
        }
        from app.transmission.state import find_by_chat_msg
        result = find_by_chat_msg("-100999", 99)
        assert result is None

    def test_match_uses_string_chat_id(self):
        """chat_id may be stored as string; ensure match works."""
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "test.mkv",
            "chat_id": "-100123", "msg_id": 42,
        }
        from app.transmission.state import find_by_chat_msg
        result = find_by_chat_msg("-100123", 42)
        assert result is not None
        assert result["id"] == 1

    def test_no_match_wrong_msg_id(self):
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "test.mkv",
            "chat_id": "-100123", "msg_id": 42,
        }
        from app.transmission.state import find_by_chat_msg
        result = find_by_chat_msg("-100123", 999)
        assert result is None

    def test_no_match_empty_state(self):
        """Empty state should return None."""
        from app.transmission.state import find_by_chat_msg
        assert find_by_chat_msg("-100123", 42) is None


# ===================================================================
# Task 1.3: _file_path serialization
# ===================================================================

class TestFilePathSerialization:
    def test_file_path_persisted_through_save_load(self, test_settings):
        """_file_path must survive a save/load roundtrip."""
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "test.mkv",
            "chat_id": "-100123", "msg_id": 42,
            "downloadDir": "/data/cache",
            "file_path": "/data/tv/test.mkv",  # NOT _file_path — see design note
        }
        save_state()
        downloads.clear()
        load_state()
        assert 1 in downloads
        assert downloads[1].get("file_path") == "/data/tv/test.mkv"

    def test_file_path_survives_snapshot(self):
        """file_path (without underscore) must appear in snapshots."""
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "test.mkv",
            "chat_id": "-100123", "msg_id": 42,
            "file_path": "/data/tv/test.mkv",
        }
        snapshot = get_downloads_snapshot()
        assert len(snapshot) == 1
        assert snapshot[0].get("file_path") == "/data/tv/test.mkv"

    def test_file_path_default_none(self):
        """New downloads without file_path should have None."""
        from app.transmission.state import find_by_chat_msg
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "test.mkv",
            "chat_id": "-100123", "msg_id": 42,
        }
        result = find_by_chat_msg("-100123", 42)
        assert result is not None
        assert result.get("file_path") is None
