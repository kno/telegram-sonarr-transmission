from unittest.mock import AsyncMock, patch

import pytest


class TestHealthEndpoint:
    async def test_health(self, async_client):
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestLifespan:
    @patch("app.main.disconnect_client", new_callable=AsyncMock)
    @patch("app.main.resume_downloads", new_callable=AsyncMock)
    @patch("app.main.init_channels", new_callable=AsyncMock)
    @patch("app.main.connect_client", new_callable=AsyncMock)
    async def test_startup_shutdown(self, mock_connect, mock_init, mock_resume, mock_disconnect):
        from app.main import lifespan
        from fastapi import FastAPI

        app = FastAPI()

        async with lifespan(app):
            mock_connect.assert_called_once()
            mock_init.assert_called_once()
            mock_resume.assert_called_once()
            mock_disconnect.assert_not_called()

        mock_disconnect.assert_called_once()
