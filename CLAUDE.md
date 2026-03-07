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

No test suite exists yet. No linter is configured.

## Architecture

The app is a single FastAPI service (`app/main:app`) with four routers:

1. **Torznab API** (`app/torznab/`) — `/api` endpoint implementing the Torznab/Newznab XML protocol. Sonarr/Prowlarr query this to search for content. Search hits Telegram channels concurrently (throttled to 3 via semaphore) and returns RSS XML.

2. **Download** (`app/download.py`) — `/api/download` returns a minimal synthetic `.torrent` file. The torrent embeds `chat_id:msg_id` in its comment field (no real BitTorrent data). Includes custom bencode/bdecode implementations.

3. **Stream** (`app/stream.py`) — `/api/stream` serves the actual file content with Range request support. Downloads from Telegram on first request, then serves from disk cache.

4. **Transmission RPC** (`app/transmission.py`) — `/transmission/rpc` emulates Transmission's JSON-RPC. When Sonarr sends a "torrent-add", it decodes the synthetic `.torrent`, extracts `chat_id:msg_id` from the comment, and downloads the file from Telegram in a background task. Reports download progress back to Sonarr via torrent-get.

### Key flow

Sonarr search → Torznab `/api?t=search` → searches Telegram channels → returns XML with download URLs → Sonarr grabs `.torrent` via `/api/download` → sends to fake Transmission RPC → extracts `chat_id:msg_id` from torrent comment → downloads file from Telegram → reports completion to Sonarr.

### Shared state

- `app/telegram_client.py` — singleton Telethon client, connected at startup
- `app/channels.py` — in-memory channel registry with JSON persistence; auto-discovers from Telegram on first run
- `app/config.py` — `pydantic-settings` config with lazy proxy (`settings` import works at module level without triggering validation)
- `app/transmission.py` — in-memory download state (`_downloads` dict), not persisted across restarts

## Configuration

All config via environment variables (see `.env.example`). Key vars: `API_ID`, `API_HASH`, `PHONE`, `TORZNAB_APIKEY`, `BASE_URL`. Config loaded via `pydantic-settings` in `app/config.py`.

## Conventions

- Python 3.12, type hints with `X | None` syntax (not `Optional`)
- Auth uses `hmac.compare_digest` for constant-time API key comparison
- Torznab errors return HTTP 200 with XML error body (per spec)
- Telegram channels are mapped to Torznab categories starting at ID 1000
- Files cached on disk as `{chat_id}_{msg_id}_{filename}` in `DOWNLOAD_DIR`
