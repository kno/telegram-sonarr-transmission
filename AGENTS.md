# Agents Guide

## Project Overview
Telegram-to-Torznab bridge and Transmission RPC emulator. Allows Sonarr/Radarr/Prowlarr to search and download directly from Telegram channels.

## Development Workflow
- **Local Dev**:
  - Install: `pip install -r requirements.txt`
  - Run: `uvicorn app.main:app --host 0.0.0.0 --port 9117 --reload`
  - Environment: `.env` file (required: `API_ID`, `API_HASH`, `PHONE`, `TORZNAB_APIKEY`, `BASE_URL`)
- **Auth**:
  - Interactive session creation: `docker compose --profile auth run --rm torznab-auth`
  - Saves Telethon metadata session to `./data/torznab_session_telethon.session` (or specified `SESSION_NAME` with `_telethon` suffix).
  - Saves or reuses Pyrogram download session at `./data/torznab_session.session`; use `--backend telethon` or `--backend pyrogram` to authenticate only one backend.
- **Frontend**:
  - Build: `cd frontend && npm run build` (static output to `frontend/build/`)
  - Dev: `cd frontend && npm run dev` (proxies API to `:9117`)

## Architecture & State
- **FastAPI**: Main entrypoint `app/main.py` with 4 key routers: `torznab/`, `download.py`, `stream.py`, `transmission/`.
- **Telegram Client**: Hybrid compatibility adapter in `app/telegram_client.py`; Telethon handles search/dialogs/metadata/API v2 browsing, Pyrogram+TgCrypto handles high-throughput download/stream fetches by `chat_id:msg_id`.
- **Channel Registry**: In-memory registry in `app/channels.py` with JSON persistence in `./data/channels.json`.
- **Download State**: Persisted in-memory state in `app/transmission/state.py` (saved to `downloads.json`).
- **Key Flow**: Search (Torznab) -> Grab (.torrent) -> Download (Transmission RPC emulator) -> Stream.

## Testing
- **Command**: `python3 -m pytest`
- **Coverage**: `python3 -m pytest --cov=app --cov-report=term-missing`
- **Migration caveat**: if system Python has no pytest installed, use `./.venv/bin/python -m pytest` (and the same venv prefix for coverage).
- **Mocks**: `tests/conftest.py` provides `mock_telegram_client` and other shared fixtures.
- **Pre-commit**: Tests run automatically before each commit.

## Conventions & Quirks
- **Python**: 3.12, type hints using `X | None` syntax.
- **Auth**: `hmac.compare_digest` for constant-time comparisons.
- **Torznab Errors**: Return HTTP 200 with XML error body.
- **Category Mapping**: Telegram channels mapped to IDs starting at 1000.
- **Filesystem Cache**: Files saved as `{chat_id}_{msg_id}_{filename}` in `DOWNLOAD_DIR`.
- **Throttling**: Telegram search hits are limited to 3 concurrent queries to avoid flood waits.
- **Synthetic Torrents**: `.torrent` files are synthetic and do not contain actual BitTorrent data.
- **Frontend**: SvelteKit 2 SPA (Svelte 5) served as static files.
