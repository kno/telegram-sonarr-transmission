from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import SPAStaticFiles


class TestSPAStaticFiles:
    """The frontend is a SvelteKit SPA built with adapter-static — only one
    HTML file (index.html) ships, so unknown routes must fall back to it for
    page reloads to work. Real asset 404s must still surface as 404."""

    def _make_client(self, tmp_path):
        index = tmp_path / "index.html"
        index.write_text("<html>SPA shell</html>")
        assets = tmp_path / "_app"
        assets.mkdir()
        (assets / "real.js").write_text("// real asset")

        app = FastAPI()
        app.mount("/", SPAStaticFiles(directory=str(tmp_path), html=True))
        return TestClient(app)

    def test_root_serves_index(self, tmp_path):
        client = self._make_client(tmp_path)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "SPA shell" in resp.text

    def test_extensionless_unknown_route_falls_back_to_index(self, tmp_path):
        # /downloads, /search, etc. must serve the SPA shell on hard reload
        client = self._make_client(tmp_path)
        for path in ("/downloads", "/search", "/channels", "/nope/deep/path"):
            resp = client.get(path)
            assert resp.status_code == 200, f"{path} returned {resp.status_code}"
            assert "SPA shell" in resp.text

    def test_real_static_asset_is_served(self, tmp_path):
        client = self._make_client(tmp_path)
        resp = client.get("/_app/real.js")
        assert resp.status_code == 200
        assert "real asset" in resp.text

    def test_missing_asset_with_extension_returns_404(self, tmp_path):
        # Don't mask broken asset references behind index.html — extensions
        # signal "this is a file request".
        client = self._make_client(tmp_path)
        for path in ("/_app/missing.js", "/styles.css", "/icon.png"):
            resp = client.get(path)
            assert resp.status_code == 404, f"{path} returned {resp.status_code}"


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
