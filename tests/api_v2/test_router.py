"""Tests for the API v2 endpoints (folder CRUD, browse, move, bulk-move)."""

import os

import pytest

APIKEY = "testapikey"


# ===================================================================
# Folder CRUD
# ===================================================================

class TestFolders:
    async def test_list_empty(self, async_client):
        resp = await async_client.get(f"/api/v2/folders?apikey={APIKEY}")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_folder(self, async_client, tmp_path):
        tv_dir = tmp_path / "tv"
        tv_dir.mkdir()
        resp = await async_client.post(
            f"/api/v2/folders?apikey={APIKEY}",
            json={"name": "TV Series", "path": str(tv_dir)},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "TV Series"
        assert data["path"] == str(tv_dir)
        assert "id" in data

    async def test_create_folder_invalid_path(self, async_client):
        resp = await async_client.post(
            f"/api/v2/folders?apikey={APIKEY}",
            json={"name": "Bad", "path": "/../etc"},
        )
        assert resp.status_code == 400

    async def test_list_after_create(self, async_client, tmp_path):
        tv_dir = tmp_path / "tv"
        tv_dir.mkdir()
        await async_client.post(
            f"/api/v2/folders?apikey={APIKEY}",
            json={"name": "TV", "path": str(tv_dir)},
        )
        resp = await async_client.get(f"/api/v2/folders?apikey={APIKEY}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "TV"

    async def test_delete_folder(self, async_client, tmp_path):
        tv_dir = tmp_path / "tv"
        tv_dir.mkdir()
        created = await async_client.post(
            f"/api/v2/folders?apikey={APIKEY}",
            json={"name": "TV", "path": str(tv_dir)},
        )
        dest_id = created.json()["id"]

        resp = await async_client.delete(f"/api/v2/folders/{dest_id}?apikey={APIKEY}")
        assert resp.status_code == 204

        # Verify it's gone
        list_resp = await async_client.get(f"/api/v2/folders?apikey={APIKEY}")
        assert list_resp.json() == []

    async def test_delete_folder_blocked_by_active_download(self, async_client, tmp_path):
        tv_dir = tmp_path / "tv"
        tv_dir.mkdir()
        created = await async_client.post(
            f"/api/v2/folders?apikey={APIKEY}",
            json={"name": "TV", "path": str(tv_dir)},
        )
        dest_id = created.json()["id"]

        # Add a non-finished download using this destination
        from app.transmission.state import get_downloads
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "test.mkv", "downloadDir": str(tv_dir),
            "status": 4, "isFinished": False,
        }

        resp = await async_client.delete(f"/api/v2/folders/{dest_id}?apikey={APIKEY}")
        assert resp.status_code == 409

    async def test_delete_folder_finished_download_allowed(self, async_client, tmp_path):
        """A completed download using the destination should NOT block deletion."""
        tv_dir = tmp_path / "tv"
        tv_dir.mkdir()
        created = await async_client.post(
            f"/api/v2/folders?apikey={APIKEY}",
            json={"name": "TV", "path": str(tv_dir)},
        )
        dest_id = created.json()["id"]

        from app.transmission.state import get_downloads
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "done.mkv", "downloadDir": str(tv_dir),
            "status": 6, "isFinished": True,
        }

        resp = await async_client.delete(f"/api/v2/folders/{dest_id}?apikey={APIKEY}")
        assert resp.status_code == 204

    async def test_delete_nonexistent_folder(self, async_client):
        resp = await async_client.delete("/api/v2/folders/nonexistent?apikey=" + APIKEY)
        assert resp.status_code == 404

    async def test_unauthorized(self, async_client):
        resp = await async_client.get("/api/v2/folders")
        assert resp.status_code == 401


# ===================================================================
# Browse
# ===================================================================

class TestBrowse:
    async def test_browse_root(self, async_client):
        resp = await async_client.get(f"/api/v2/browse?path=/&apikey={APIKEY}")
        assert resp.status_code == 200
        data = resp.json()
        assert "entries" in data
        assert len(data["entries"]) > 0

    async def test_browse_valid_path(self, async_client, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "file.txt").write_text("hello")
        resp = await async_client.get(f"/api/v2/browse?path={sub}&apikey={APIKEY}")
        assert resp.status_code == 200
        data = resp.json()
        names = {e["name"] for e in data["entries"]}
        assert "file.txt" in names

    async def test_browse_traversal_rejected(self, async_client):
        resp = await async_client.get(f"/api/v2/browse?path=/../etc&apikey={APIKEY}")
        assert resp.status_code == 403

    async def test_browse_permission_error(self, async_client, tmp_path):
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        restricted.chmod(0o000)
        try:
            resp = await async_client.get(f"/api/v2/browse?path={restricted}&apikey={APIKEY}")
            assert resp.status_code == 200
            data = resp.json()
            assert "error" in data
            assert len(data["entries"]) == 0
        finally:
            restricted.chmod(0o755)

    async def test_browse_nonexistent_path(self, async_client):
        resp = await async_client.get(
            f"/api/v2/browse?path=/tmp/nonexistent_path_12345_test&apikey={APIKEY}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert len(data["entries"]) == 0

    async def test_browse_show_hidden(self, async_client, tmp_path):
        (tmp_path / ".hidden_file").write_text("secret")
        (tmp_path / "visible.txt").write_text("hello")
        resp = await async_client.get(
            f"/api/v2/browse?path={tmp_path}&show_hidden=true&apikey={APIKEY}"
        )
        assert resp.status_code == 200
        data = resp.json()
        names = {e["name"] for e in data["entries"]}
        assert ".hidden_file" in names
        assert "visible.txt" in names

    async def test_browse_hidden_excluded_by_default(self, async_client, tmp_path):
        (tmp_path / ".hidden_file").write_text("secret")
        resp = await async_client.get(
            f"/api/v2/browse?path={tmp_path}&apikey={APIKEY}"
        )
        data = resp.json()
        names = {e["name"] for e in data["entries"]}
        assert ".hidden_file" not in names


# ===================================================================
# Move Download
# ===================================================================

class TestMoveDownload:
    async def _create_destination(self, async_client, tmp_path, name="TV"):
        tv_dir = tmp_path / name.lower()
        tv_dir.mkdir(parents=True, exist_ok=True)
        resp = await async_client.post(
            f"/api/v2/folders?apikey={APIKEY}",
            json={"name": name, "path": str(tv_dir)},
        )
        return resp.json()["id"], str(tv_dir)

    async def test_move_completed(self, async_client, tmp_path):
        dest_id, tv_path = await self._create_destination(async_client, tmp_path)

        old_dir = tmp_path / "cache"
        old_dir.mkdir()
        file_path = old_dir / "video.mkv"
        file_path.write_text("content")

        from app.transmission.state import get_downloads
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "video.mkv", "downloadDir": str(old_dir),
            "status": 6, "isFinished": True,
        }

        resp = await async_client.post(
            f"/api/v2/downloads/1/move?apikey={APIKEY}",
            json={"destination_id": dest_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "moved"

        # File moved
        assert not file_path.exists()
        assert os.path.exists(os.path.join(tv_path, "video.mkv"))
        # State updated
        assert downloads[1]["downloadDir"] == tv_path
        assert downloads[1]["file_path"] == os.path.join(tv_path, "video.mkv")

    async def test_move_pending(self, async_client, tmp_path):
        dest_id, tv_path = await self._create_destination(async_client, tmp_path)

        old_dir = tmp_path / "cache"
        old_dir.mkdir()

        from app.transmission.state import get_downloads
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "pending.mkv", "downloadDir": str(old_dir),
            "status": 4, "isFinished": False,
        }

        resp = await async_client.post(
            f"/api/v2/downloads/1/move?apikey={APIKEY}",
            json={"destination_id": dest_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "moved"
        # downloadDir updated but no file moved
        assert downloads[1]["downloadDir"] == tv_path
        # file_path updated to new location
        assert downloads[1]["file_path"] == os.path.join(tv_path, "pending.mkv")

    async def test_move_nonexistent_download(self, async_client, tmp_path):
        dest_id, _ = await self._create_destination(async_client, tmp_path)
        resp = await async_client.post(
            f"/api/v2/downloads/999/move?apikey={APIKEY}",
            json={"destination_id": dest_id},
        )
        assert resp.status_code == 404

    async def test_move_nonexistent_destination(self, async_client):
        from app.transmission.state import get_downloads
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "test.mkv", "downloadDir": "/tmp",
            "status": 6, "isFinished": True,
        }
        resp = await async_client.post(
            "/api/v2/downloads/1/move?apikey=" + APIKEY,
            json={"destination_id": "does-not-exist"},
        )
        assert resp.status_code == 404

    async def test_move_file_not_found(self, async_client, tmp_path):
        """Completed download with missing file should still update state but report error."""
        dest_id, tv_path = await self._create_destination(async_client, tmp_path)

        old_dir = tmp_path / "cache"
        old_dir.mkdir()

        from app.transmission.state import get_downloads
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "missing.mkv", "downloadDir": str(old_dir),
            "status": 6, "isFinished": True,
        }

        resp = await async_client.post(
            f"/api/v2/downloads/1/move?apikey={APIKEY}",
            json={"destination_id": dest_id},
        )
        # File not found — still update state? or error? Let's say error with 500
        assert resp.status_code == 500
        assert downloads[1]["downloadDir"] == str(old_dir)  # unchanged


# ===================================================================
# Bulk Move
# ===================================================================

class TestBulkMove:
    async def _create_destination(self, async_client, tmp_path, name="TV"):
        tv_dir = tmp_path / name.lower()
        tv_dir.mkdir(parents=True, exist_ok=True)
        resp = await async_client.post(
            f"/api/v2/folders?apikey={APIKEY}",
            json={"name": name, "path": str(tv_dir)},
        )
        return resp.json()["id"], str(tv_dir)

    async def test_bulk_all_succeed(self, async_client, tmp_path):
        dest_id, tv_path = await self._create_destination(async_client, tmp_path)

        old_dir = tmp_path / "cache"
        old_dir.mkdir()
        (old_dir / "a.mkv").write_text("a")
        (old_dir / "b.mkv").write_text("b")

        from app.transmission.state import get_downloads
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "a.mkv", "downloadDir": str(old_dir),
            "status": 6, "isFinished": True,
        }
        downloads[2] = {
            "id": 2, "name": "b.mkv", "downloadDir": str(old_dir),
            "status": 6, "isFinished": True,
        }

        resp = await async_client.post(
            f"/api/v2/downloads/bulk-move?apikey={APIKEY}",
            json={"ids": [1, 2], "destination_id": dest_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        assert all(r["status"] == "moved" for r in data["results"])

        # Verify files moved
        assert os.path.exists(os.path.join(tv_path, "a.mkv"))
        assert os.path.exists(os.path.join(tv_path, "b.mkv"))
        assert not (old_dir / "a.mkv").exists()

    async def test_bulk_partial_success(self, async_client, tmp_path):
        dest_id, tv_path = await self._create_destination(async_client, tmp_path)

        old_dir = tmp_path / "cache"
        old_dir.mkdir()
        (old_dir / "a.mkv").write_text("a")

        from app.transmission.state import get_downloads
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "a.mkv", "downloadDir": str(old_dir),
            "status": 6, "isFinished": True,
        }
        downloads[2] = {
            "id": 2, "name": "missing.mkv", "downloadDir": str(old_dir),
            "status": 6, "isFinished": True,
        }

        resp = await async_client.post(
            f"/api/v2/downloads/bulk-move?apikey={APIKEY}",
            json={"ids": [1, 2], "destination_id": dest_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 2
        results_by_id = {r["id"]: r for r in data["results"]}
        assert results_by_id[1]["status"] == "moved"
        assert results_by_id[2]["status"] == "error"

    async def test_bulk_nonexistent_destination(self, async_client):
        resp = await async_client.post(
            f"/api/v2/downloads/bulk-move?apikey={APIKEY}",
            json={"ids": [1], "destination_id": "no-such-dest"},
        )
        assert resp.status_code == 404
