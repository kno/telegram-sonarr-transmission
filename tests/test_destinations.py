import json
import os

import pytest

from app.config import settings
from app.destinations import Destination, DestinationsManager, list_dir


@pytest.fixture(autouse=True)
def _ensure_settings(monkeypatch, tmp_path):
    """Ensure env vars are set so the Settings proxy doesn't fail.

    Tests that need ``test_settings`` for full isolation can still use it;
    this just provides a baseline so plain unit tests can access
    ``settings.DESTINATIONS_FILE`` without crashing.
    """
    monkeypatch.setenv("API_ID", "12345")
    monkeypatch.setenv("API_HASH", "testhash")
    monkeypatch.setenv("TORZNAB_APIKEY", "testapikey")
    monkeypatch.setenv("BASE_URL", "http://localhost:9117")
    from app.config import get_settings
    get_settings.cache_clear()
    # Point DESTINATIONS_FILE to a unique path for this test
    monkeypatch.setattr(settings, "DESTINATIONS_FILE", str(tmp_path / "destinations.json"))


# ===================================================================
# Task 1.1: DESTINATIONS_FILE config
# ===================================================================

class TestDestinationsConfig:
    def test_destinations_file_exists(self):
        """DESTINATIONS_FILE must be defined in settings."""
        assert hasattr(settings, "DESTINATIONS_FILE")
        assert isinstance(settings.DESTINATIONS_FILE, str)
        assert settings.DESTINATIONS_FILE.endswith(".json")


# ===================================================================
# Task 1.2: Destination dataclass
# ===================================================================

class TestDestinationDataclass:
    def test_create_destination(self):
        d = Destination(id="abc123", name="Series", path="/data/tv", created_at="2025-01-01T00:00:00")
        assert d.id == "abc123"
        assert d.name == "Series"
        assert d.path == "/data/tv"
        assert d.created_at == "2025-01-01T00:00:00"

    def test_repr(self):
        d = Destination(id="x", name="Movies", path="/data/movies", created_at="now")
        r = repr(d)
        assert "Destination" in r
        assert "Movies" in r


# ===================================================================
# Task 1.2: DestinationsManager CRUD
# ===================================================================

class TestDestinationsManager:
    def test_list_empty(self):
        mgr = DestinationsManager()
        assert mgr.list() == []

    def test_add_and_list(self, tmp_path):
        tv_dir = tmp_path / "tv"
        tv_dir.mkdir()
        mgr = DestinationsManager()
        dest = mgr.add(name="Series", path=str(tv_dir))
        assert dest.name == "Series"
        assert os.path.isabs(dest.path)
        assert dest.id is not None
        all_dests = mgr.list()
        assert len(all_dests) == 1
        assert all_dests[0].name == "Series"

    def test_add_creates_uuid(self, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        mgr = DestinationsManager()
        d1 = mgr.add("A", str(tmp_path / "a"))
        d2 = mgr.add("B", str(tmp_path / "b"))
        assert d1.id != d2.id

    def test_get_by_id(self, tmp_path):
        (tmp_path / "tv").mkdir()
        mgr = DestinationsManager()
        added = mgr.add("Series", str(tmp_path / "tv"))
        found = mgr.get(added.id)
        assert found is not None
        assert found.name == "Series"
        assert found.path == str(tmp_path / "tv")

    def test_get_nonexistent(self):
        mgr = DestinationsManager()
        assert mgr.get("nonexistent") is None

    def test_remove(self, tmp_path):
        (tmp_path / "tv").mkdir()
        (tmp_path / "movies").mkdir()
        mgr = DestinationsManager()
        d1 = mgr.add("Series", str(tmp_path / "tv"))
        d2 = mgr.add("Movies", str(tmp_path / "movies"))
        assert len(mgr.list()) == 2
        mgr.remove(d1.id)
        assert len(mgr.list()) == 1
        assert mgr.get(d1.id) is None
        assert mgr.get(d2.id) is not None

    def test_remove_nonexistent_does_not_raise(self):
        mgr = DestinationsManager()
        mgr.remove("no-such-id")  # should not raise
        assert mgr.list() == []

    def test_get_by_path(self, tmp_path):
        (tmp_path / "tv").mkdir()
        mgr = DestinationsManager()
        mgr.add("Series", str(tmp_path / "tv"))
        found = mgr.get_by_path(str(tmp_path / "tv"))
        assert found is not None
        assert found.name == "Series"

    def test_get_by_path_no_match(self):
        mgr = DestinationsManager()
        assert mgr.get_by_path("/nonexistent") is None


# ===================================================================
# Task 1.2: Path validation
# ===================================================================

class TestDestinationsPathValidation:
    def test_reject_traversal(self):
        mgr = DestinationsManager()
        with pytest.raises(ValueError, match="(?i)path traversal"):
            mgr.add("Bad", "/data/../etc")

    def test_reject_traversal_nested(self):
        mgr = DestinationsManager()
        with pytest.raises(ValueError, match="(?i)path traversal"):
            mgr.add("Bad", "/data/foo/../../../etc")

    def test_accept_normal_path(self, tmp_path):
        sub = tmp_path / "valid_dir"
        sub.mkdir()
        mgr = DestinationsManager()
        dest = mgr.add("Valid", str(sub))
        assert dest.path == str(sub)
        assert mgr.get_by_path(str(sub)) is not None


# ===================================================================
# Task 1.2: Persistence (save/load roundtrip)
# ===================================================================

class TestDestinationsPersistence:
    def test_save_creates_file(self, tmp_path):
        dest_file = tmp_path / "destinations.json"
        (tmp_path / "tv").mkdir()
        mgr = DestinationsManager()
        mgr.add("Series", str(tmp_path / "tv"))
        assert dest_file.exists()

    def test_load_restores_data(self, tmp_path):
        (tmp_path / "tv").mkdir()
        (tmp_path / "movies").mkdir()
        mgr1 = DestinationsManager()
        mgr1.add("Series", str(tmp_path / "tv"))
        mgr1.add("Movies", str(tmp_path / "movies"))

        mgr2 = DestinationsManager()
        all_dests = mgr2.list()
        assert len(all_dests) == 2
        names = {d.name for d in all_dests}
        assert names == {"Series", "Movies"}

    def test_save_file_content(self, tmp_path):
        dest_file = tmp_path / "destinations.json"
        (tmp_path / "tv").mkdir()
        mgr = DestinationsManager()
        mgr.add("Series", str(tmp_path / "tv"))
        with open(dest_file) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["name"] == "Series"
        assert "id" in data[0]
        assert "path" in data[0]
        assert "created_at" in data[0]

    def test_load_missing_file(self, tmp_path):
        """Loading with no file should not raise and should return empty."""
        # The autouse fixture points DESTINATIONS_FILE to a unique path.
        # This test relies on that file not existing yet.
        mgr = DestinationsManager()
        assert mgr.list() == []

    def test_remove_then_load_reflects(self, tmp_path):
        (tmp_path / "tv").mkdir()
        mgr1 = DestinationsManager()
        d = mgr1.add("Series", str(tmp_path / "tv"))
        mgr1.remove(d.id)

        mgr2 = DestinationsManager()
        assert mgr2.list() == []


# ===================================================================
# Task 1.2: list_dir file browser
# ===================================================================

class TestListDir:
    def test_list_valid_directory(self, tmp_path):
        """Should list entries (files and dirs) in a valid directory."""
        (tmp_path / "file1.txt").write_text("hello")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.txt").write_text("nested")

        result = list_dir(str(tmp_path), show_hidden=False)
        entries = {e["name"] for e in result["entries"]}
        assert "file1.txt" in entries
        assert "subdir" in entries

    def test_entries_have_types(self, tmp_path):
        (tmp_path / "afile.txt").write_text("x")
        (tmp_path / "adir").mkdir()
        result = list_dir(str(tmp_path), show_hidden=False)
        for e in result["entries"]:
            if e["name"] == "afile.txt":
                assert e["type"] == "file"
            elif e["name"] == "adir":
                assert e["type"] == "dir"

    def test_entries_have_full_paths(self, tmp_path):
        (tmp_path / "hello.txt").write_text("x")
        result = list_dir(str(tmp_path), show_hidden=False)
        for e in result["entries"]:
            if e["name"] == "hello.txt":
                assert e["path"] == str(tmp_path / "hello.txt")

    def test_rejects_traversal(self, tmp_path):
        result = list_dir(str(tmp_path / ".." / ".."), show_hidden=False)
        assert "error" in result
        assert "error" not in result.get("entries", [])
        # Should also set entries to empty
        assert len(result.get("entries", [])) == 0

    def test_rejects_absolute_traversal(self):
        result = list_dir("/etc/../..", show_hidden=False)
        assert "error" in result
        assert len(result.get("entries", [])) == 0

    def test_nonexistent_directory(self, tmp_path):
        result = list_dir(str(tmp_path / "does_not_exist"), show_hidden=False)
        assert "error" in result
        assert len(result.get("entries", [])) == 0

    def test_hidden_files_excluded_by_default(self, tmp_path):
        (tmp_path / ".hidden_file").write_text("secret")
        (tmp_path / "visible.txt").write_text("hello")
        result = list_dir(str(tmp_path), show_hidden=False)
        entry_names = {e["name"] for e in result["entries"]}
        assert "visible.txt" in entry_names
        assert ".hidden_file" not in entry_names

    def test_hidden_files_included_when_requested(self, tmp_path):
        (tmp_path / ".hidden_file").write_text("secret")
        (tmp_path / "visible.txt").write_text("hello")
        result = list_dir(str(tmp_path), show_hidden=True)
        entry_names = {e["name"] for e in result["entries"]}
        assert "visible.txt" in entry_names
        assert ".hidden_file" in entry_names

    def test_allows_symlink_detection(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("x")
        link = tmp_path / "mylink"
        os.symlink(target, link)
        result = list_dir(str(tmp_path), show_hidden=False)
        for e in result["entries"]:
            if e["name"] == "mylink":
                assert e["type"] == "symlink"
                return
        pytest.fail("symlink entry not found")

    def test_absolute_path_resolved_not_allowed(self):
        """A path that resolves outside its root must be rejected."""
        # /var/../etc resolves to /etc - if the "root" is /var, this is a traversal
        result = list_dir("/var/../etc", show_hidden=False)
        assert "error" in result

    def test_root_slash_allowed(self):
        """Root / should be allowed (most basic path)."""
        result = list_dir("/", show_hidden=False)
        # / always has entries
        assert "entries" in result
        assert len(result["entries"]) > 0

    def test_file_path_rejected(self, tmp_path):
        """A path pointing to a file, not a directory, must return error."""
        f = tmp_path / "just_a_file.txt"
        f.write_text("x")
        result = list_dir(str(f), show_hidden=False)
        assert "error" in result

    def test_permission_error_handled(self, tmp_path, monkeypatch):
        """Permission errors should return an error message, not crash."""
        # We can simulate by making a dir non-readable
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o000)
        try:
            result = list_dir(str(restricted), show_hidden=False)
            assert "error" in result
        finally:
            # Restore permissions so cleanup works
            restricted.chmod(0o755)

    def test_per_entry_permission_error(self, tmp_path, monkeypatch):
        """When one entry is unreadable, other entries should still be returned."""
        (tmp_path / "good.txt").write_text("hello")
        restricted = tmp_path / "restricted_dir"
        restricted.mkdir()
        restricted.chmod(0o000)
        try:
            result = list_dir(str(tmp_path), show_hidden=False)
            entry_names = {e["name"] for e in result["entries"]}
            assert "good.txt" in entry_names
            # restricted dir might fail during stat - that's OK
        finally:
            restricted.chmod(0o755)
