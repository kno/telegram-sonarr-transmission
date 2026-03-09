# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Telegram-to-Torznab bridge that exposes Telegram channels as a Torznab-compatible indexer for Sonarr/Radarr/Prowlarr. It also emulates a Transmission RPC server so Sonarr/Radarr can trigger downloads that are actually fetched from Telegram.

## Running

```bash
# First-time auth (interactive, generates Telegram .session file)
docker compose --profile auth run --rm torznab-auth

# Run the server
docker compose up -d

# Run locally (dev)
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 9117 --reload
```

## Testing

```bash
# Run all tests
python3 -m pytest

# With coverage report
python3 -m pytest --cov=app --cov-report=term-missing

# Run specific module tests
python3 -m pytest tests/test_download.py -v
python3 -m pytest tests/torznab/ -v
python3 -m pytest tests/transmission/ -v
```

- 196 tests across 16 files, 92% overall coverage
- Uses `pytest` + `pytest-asyncio` + `httpx` (AsyncClient for FastAPI)
- All Telegram API calls mocked via `AsyncMock` (no real connection needed)
- Filesystem tests use pytest `tmp_path` fixture
- Shared fixtures in `tests/conftest.py`: `test_settings`, `mock_telegram_client`, `mock_message`, `populated_channels`, `clean_downloads`, `test_app`, `async_client`
- Pre-commit hook runs tests before every commit
- Dev dependencies: `pip install -r requirements-dev.txt`

No linter is configured.

## Architecture

The app is a single FastAPI service (`app/main:app`) with four routers:

1. **Torznab API** (`app/torznab/`) — `/api` endpoint implementing the Torznab/Newznab XML protocol. Sonarr/Prowlarr query this to search for content. Search hits Telegram channels concurrently (throttled to 3 via semaphore) and returns RSS XML.

2. **Download** (`app/download.py`) — `/api/download` returns a minimal synthetic `.torrent` file. The torrent embeds `chat_id:msg_id` in its comment field (no real BitTorrent data). Includes custom bencode/bdecode implementations.

3. **Stream** (`app/stream.py`) — `/api/stream` serves the actual file content with Range request support. Downloads from Telegram on first request, then serves from disk cache.

4. **Transmission RPC** (`app/transmission/`) — `/transmission/rpc` emulates Transmission's JSON-RPC. When Sonarr sends a "torrent-add", it decodes the synthetic `.torrent`, extracts `chat_id:msg_id` from the comment, and downloads the file from Telegram in a background task. Reports download progress back to Sonarr via torrent-get. Package split into `router.py`, `handlers.py`, `state.py`, `downloader.py`, `websocket.py`.

### Key flow

Sonarr search → Torznab `/api?t=search` → searches Telegram channels → returns XML with download URLs → Sonarr grabs `.torrent` via `/api/download` → sends to fake Transmission RPC → extracts `chat_id:msg_id` from torrent comment → downloads file from Telegram → reports completion to Sonarr.

5. **Web UI** (`frontend/`) — SvelteKit 2 SPA (Svelte 5 + Tailwind CSS 4 + TypeScript) built to static files and served by FastAPI from `frontend/build/`. Provides dashboard, search, downloads (with live WebSocket progress), channel management, and settings pages. All UI text is in Spanish.

### Shared state

- `app/telegram_client.py` — singleton Pyrogram client, connected at startup
- `app/channels.py` — in-memory channel registry with JSON persistence; auto-discovers from Telegram on first run
- `app/config.py` — `pydantic-settings` config with lazy proxy (`settings` import works at module level without triggering validation)
- `app/transmission/state.py` — in-memory download state (`_downloads` dict), persisted to `downloads.json`

## Configuration

All config via environment variables (see `.env.example`). Key vars: `API_ID`, `API_HASH`, `PHONE`, `TORZNAB_APIKEY`, `BASE_URL`. Config loaded via `pydantic-settings` in `app/config.py`.

## Frontend

- **Stack:** SvelteKit 2, Svelte 5 (runes), Tailwind CSS 4, TypeScript, Vite 6
- **Adapter:** `adapter-static` — outputs to `frontend/build/`, served by FastAPI at `/`
- **State:** Svelte 5 reactive stores in `frontend/src/lib/stores.svelte.ts` (settings, channels, theme). Persisted to localStorage.
- **API layer:** `frontend/src/lib/api.ts` — all backend calls (Torznab XML parsing via `fast-xml-parser`, Transmission RPC, WebSocket at `/ws/downloads`)
- **Routes:** `/` (dashboard), `/search`, `/downloads`, `/channels`, `/settings`
- **Components:** `frontend/src/lib/components/` — Navbar, SearchResultCard, DownloadRow, ProgressBar, ThemeToggle
- **Dev proxy:** Vite proxies `/api` and `/transmission` to `localhost:9117`
- **Build:** `cd frontend && npm run build` (no Node.js needed at runtime)

## Conventions

- Python 3.12, type hints with `X | None` syntax (not `Optional`)
- Auth uses `hmac.compare_digest` for constant-time API key comparison
- Torznab errors return HTTP 200 with XML error body (per spec)
- Telegram channels are mapped to Torznab categories starting at ID 1000
- Files cached on disk as `{chat_id}_{msg_id}_{filename}` in `DOWNLOAD_DIR`
