# Design: Migrate from Pyrogram to Telethon

## Technical Approach

Replace Pyrogram with Telethon behind a thin app-owned compatibility adapter in `app/telegram_client.py`. Keep current call sites mostly stable (`get_messages`, `search_messages`, `get_chat_history`, `download_media`, `stream_media`) while converting Telethon entities/messages into the Pyrogram-shaped attributes already consumed by search, channel browsing, torrent creation, streaming, and the Transmission worker. This implements the proposal with minimum product-surface change and preserves the hard delivery gate: automated tests are required, but commits remain blocked until real Telegram channel searches pass with real credentials.

## Architecture Decisions

| Decision | Choice | Alternatives considered | Rationale |
|---|---|---|---|
| Telegram boundary | Introduce a `TelegramAdapter` owned by `app/telegram_client.py` and return it from `get_client()` | Rewrite every caller to native Telethon; introduce full domain DTOs now | Existing callers are tightly coupled to Pyrogram-shaped methods. A thin adapter localizes Telethon differences and reduces regression risk before real-channel verification. |
| Message shape | Normalize Telethon messages to small wrappers exposing current attributes (`id`, `text`, `caption`, `date`, `document/video/audio/photo`, `chat`, sender/topic fields, `empty`) | Teach `app.media`, search, stream, and API v2 to understand Telethon internals | Current tests and flows rely on those attributes. Compatibility wrappers keep `extract_media_info()` and pairing behavior stable. |
| Session strategy | Use Telethon-specific session files and do not overwrite Pyrogram sessions silently | Reuse `SESSION_NAME` unchanged; migrate old sessions | Session formats are incompatible. Preserve rollback by backing up or naming Telethon sessions explicitly. |
| Streaming | Implement adapter `stream_media(message, offset=chunk_offset)` using Telethon `iter_download()` with byte offset `offset * 1MiB` | Replace Transmission resume math; use full `download_media()` only | Download state resumes on 1 MiB chunk alignment today. The adapter must preserve this contract and verify throughput/regression risk. |
| Flood waits | Map Telethon `FloodWaitError.seconds` to existing retry/timeout semantics and keep current search semaphores | Increase concurrency; expose raw Telethon exceptions | Searches already avoid `get_chat()` on hot paths to reduce flood waits. Migration should not expand Telegram call volume. |

## Data Flow

```text
FastAPI lifespan -> connect_client() -> TelegramAdapter(TelethonClient)
Torznab/API v2 search -> adapter.search_messages() -> wrapped messages
  -> paired adapter.get_messages(id+1) -> extract_media_info() -> RSS/JSON
Download/stream/Transmission -> adapter.get_messages() -> adapter.download_media()/stream_media()
```

Channel discovery still loads dialogs at startup to resolve numeric private channels and can reuse dialog data for `channels.json` bootstrap.

## File Changes

| File | Action | Description |
|---|---|---|
| `requirements.txt` | Modify | Replace `pyrogram`/`tgcrypto` with `telethon`. |
| `Dockerfile` | Modify | Remove Pyrogram/TgCrypto assumptions; keep only dependencies Telethon and uvicorn need on Alpine. |
| `scripts/auth.py` | Modify | Authenticate with Telethon, support 2FA, write Telethon session safely. |
| `app/telegram_client.py` | Modify | Own adapter, lifecycle, entity/dialog cache, wrappers, thumbnails, channel helpers. |
| `app/media.py` | Modify | Support wrapped Telethon media fields while preserving current return contract. |
| `app/channels.py` | Modify | Replace `pyrogram.enums.ChatType` with adapter-neutral dialog/channel detection. |
| `app/torznab/search.py` | Modify | Keep API stable; only adjust for adapter exceptions/text fields if needed. |
| `app/download.py`, `app/stream.py`, `app/transmission/downloader.py`, `app/api_v2/router.py` | Modify | Preserve current calls; update log text and edge handling only if adapter contract requires it. |
| `tests/` | Modify | Remove Pyrogram import workaround and mock the adapter surface. |
| `README.md`, `AGENTS.md`, `openspec/config.yaml` | Modify | Update dependency/session/testing references from Pyrogram to Telethon. |

## Interfaces / Contracts

`get_client()` returns an object with:

```python
async def get_messages(chat_id: int, msg_id: int): ...
def search_messages(chat_id: int, query: str, limit: int): ...  # async iterator
def get_chat_history(chat_id: int, limit: int, offset_id: int = 0): ...
async def download_media(message_or_media, file_name: str): ...
def stream_media(message, offset: int = 0): ...  # async iterator of bytes
```

No new persisted application state is required beyond Telethon session files. Existing `channels.json` and `downloads.json` formats remain unchanged.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Adapter lifecycle, wrappers, media extraction, session path, flood-wait mapping | `pytest` with `AsyncMock`; no real Telegram connections. |
| Integration | Torznab/API v2 search, paired-message lookup, torrent creation, stream fallback, Transmission resume | Existing FastAPI/httpx and downloader tests updated to adapter mocks. |
| Operational gate | Real credentials authenticate and real channels return search results | Manual smoke: create Telethon session, start service with real `channels.json`, run Torznab/API v2 search, verify at least one `chat_id:msg_id` fetches a synthetic torrent; no commits before this passes. |

## Migration / Rollout

No data migration for `channels.json` or `downloads.json`. Create a fresh Telethon session and preserve existing Pyrogram session for rollback. Rollout order: update dependencies/auth, implement adapter, update tests/docs, run automated tests, then perform the real-channel search smoke gate before any commit.

## Open Questions

- [ ] Which Telethon session filename convention should be used by default: reuse `SESSION_NAME` after explicit backup, or append a Telethon suffix?
