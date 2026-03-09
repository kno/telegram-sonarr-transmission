import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.transmission.websocket as ws_mod
from app.transmission.websocket import broadcast_downloads, get_ws_clients


@pytest.fixture(autouse=True)
def _reset_ws():
    old = ws_mod._ws_clients.copy()
    ws_mod._ws_clients.clear()
    yield
    ws_mod._ws_clients.clear()
    ws_mod._ws_clients.update(old)


class TestBroadcast:
    async def test_no_clients(self):
        # Should not raise
        await broadcast_downloads()

    async def test_sends_to_all(self, monkeypatch):
        monkeypatch.setattr(
            "app.transmission.websocket.get_downloads_snapshot",
            lambda: [{"id": 1, "name": "test"}],
        )
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws_mod._ws_clients.add(ws1)
        ws_mod._ws_clients.add(ws2)

        await broadcast_downloads()

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()
        data = json.loads(ws1.send_text.call_args[0][0])
        assert data["type"] == "downloads"
        assert len(data["downloads"]) == 1

    async def test_removes_dead_clients(self, monkeypatch):
        monkeypatch.setattr(
            "app.transmission.websocket.get_downloads_snapshot",
            lambda: [],
        )
        alive = AsyncMock()
        dead = AsyncMock()
        dead.send_text = AsyncMock(side_effect=Exception("connection closed"))
        ws_mod._ws_clients.add(alive)
        ws_mod._ws_clients.add(dead)

        await broadcast_downloads()

        assert alive in ws_mod._ws_clients
        assert dead not in ws_mod._ws_clients

    async def test_data_format(self, monkeypatch):
        monkeypatch.setattr(
            "app.transmission.websocket.get_downloads_snapshot",
            lambda: [{"id": 1}, {"id": 2}],
        )
        ws = AsyncMock()
        ws_mod._ws_clients.add(ws)
        await broadcast_downloads()
        data = json.loads(ws.send_text.call_args[0][0])
        assert data["type"] == "downloads"
        assert isinstance(data["downloads"], list)
        assert len(data["downloads"]) == 2
