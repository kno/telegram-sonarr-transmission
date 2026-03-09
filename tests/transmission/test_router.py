import base64
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.transmission.router import SESSION_ID
from app.transmission.state import get_downloads


class TestRpcGet:
    async def test_returns_409_with_session_id(self, async_client):
        auth = base64.b64encode(b"user:testapikey").decode()
        resp = await async_client.get(
            "/transmission/rpc",
            headers={"Authorization": f"Basic {auth}"},
        )
        assert resp.status_code == 409
        assert resp.headers["x-transmission-session-id"] == SESSION_ID

    async def test_bad_auth(self, async_client):
        auth = base64.b64encode(b"user:wrongkey").decode()
        resp = await async_client.get(
            "/transmission/rpc",
            headers={"Authorization": f"Basic {auth}"},
        )
        assert resp.status_code == 401


class TestRpcPost:
    def _headers(self):
        auth = base64.b64encode(b"user:testapikey").decode()
        return {
            "Authorization": f"Basic {auth}",
            "X-Transmission-Session-Id": SESSION_ID,
        }

    async def test_no_session_id(self, async_client):
        auth = base64.b64encode(b"user:testapikey").decode()
        resp = await async_client.post(
            "/transmission/rpc",
            headers={"Authorization": f"Basic {auth}"},
            json={"method": "session-get"},
        )
        assert resp.status_code == 409
        assert "x-transmission-session-id" in resp.headers

    async def test_session_get(self, async_client):
        resp = await async_client.post(
            "/transmission/rpc",
            headers=self._headers(),
            json={"method": "session-get", "arguments": {}},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == "success"
        assert "version" in data["arguments"]

    async def test_unknown_method(self, async_client):
        resp = await async_client.post(
            "/transmission/rpc",
            headers=self._headers(),
            json={"method": "nonexistent"},
        )
        data = resp.json()
        assert data["result"] == "method not recognized"

    async def test_with_tag(self, async_client):
        resp = await async_client.post(
            "/transmission/rpc",
            headers=self._headers(),
            json={"method": "session-get", "tag": 42},
        )
        data = resp.json()
        assert data["tag"] == 42

    async def test_bad_auth(self, async_client):
        auth = base64.b64encode(b"user:wrong").decode()
        resp = await async_client.post(
            "/transmission/rpc",
            headers={
                "Authorization": f"Basic {auth}",
                "X-Transmission-Session-Id": SESSION_ID,
            },
            json={"method": "session-get"},
        )
        assert resp.status_code == 401


class TestServeDownload:
    async def test_success(self, async_client, tmp_path, test_settings):
        downloads = get_downloads()
        file_path = tmp_path / "cache" / "video.mkv"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"file_content_here")
        downloads[1] = {
            "id": 1, "name": "video.mkv",
            "downloadDir": str(tmp_path / "cache"),
            "isFinished": True,
        }
        resp = await async_client.get("/transmission/files/1", params={"apikey": "testapikey"})
        assert resp.status_code == 200
        assert resp.content == b"file_content_here"

    async def test_not_found(self, async_client):
        resp = await async_client.get("/transmission/files/999", params={"apikey": "testapikey"})
        assert resp.status_code == 404

    async def test_not_finished(self, async_client):
        downloads = get_downloads()
        downloads[1] = {"id": 1, "name": "x", "downloadDir": "/tmp", "isFinished": False}
        resp = await async_client.get("/transmission/files/1", params={"apikey": "testapikey"})
        assert resp.status_code == 400

    async def test_file_missing_on_disk(self, async_client, tmp_path):
        downloads = get_downloads()
        downloads[1] = {
            "id": 1, "name": "gone.mkv",
            "downloadDir": str(tmp_path),
            "isFinished": True,
        }
        resp = await async_client.get("/transmission/files/1", params={"apikey": "testapikey"})
        assert resp.status_code == 404

    async def test_auth_basic(self, async_client, tmp_path):
        downloads = get_downloads()
        file_path = tmp_path / "cache" / "video.mkv"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"data")
        downloads[1] = {
            "id": 1, "name": "video.mkv",
            "downloadDir": str(tmp_path / "cache"),
            "isFinished": True,
        }
        auth = base64.b64encode(b"user:testapikey").decode()
        resp = await async_client.get(
            "/transmission/files/1",
            headers={"Authorization": f"Basic {auth}"},
        )
        assert resp.status_code == 200

    async def test_auth_bad_apikey(self, async_client):
        resp = await async_client.get("/transmission/files/1", params={"apikey": "wrong"})
        assert resp.status_code == 401
