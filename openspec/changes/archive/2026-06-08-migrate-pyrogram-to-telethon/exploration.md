## Exploration: Migrate from Pyrogram to Telethon

### Current State
The backend centralizes Telegram lifecycle and channel browsing helpers in `app/telegram_client.py`, but downstream code still calls Pyrogram-shaped methods directly through `get_client()`. Startup creates a singleton `pyrogram.Client`, starts it, calls `get_me()`, and preloads dialogs to make numeric channel IDs work immediately.

The main runtime flow is: Torznab/API v2 search resolves configured channels, calls `client.search_messages()`, pairs text-only matches with `get_messages(id + 1)`, extracts media metadata, returns a synthetic torrent, then the Transmission emulator later fetches the same message and downloads it through `stream_media()`. Channel browsing uses `get_chat_history()` with `offset_id`, thumbnails use Pyrogram media `thumbs`, and fallback streaming uses `download_media()`.

Session creation is Pyrogram-specific: `scripts/auth.py` creates `./data/{SESSION_NAME}.session` with `Client(..., phone_number=PHONE)`. Requirements currently install `pyrogram` and `tgcrypto`. Tests fully mock Pyrogram-shaped APIs and do not exercise real Telegram; the user's commit gate therefore requires a separate real-credential smoke verification before any commit.

There is prior repository history showing the project migrated from Telethon to Pyrogram for faster downloads (`c4ea887`, "Migrate from Telethon to Pyrogram for faster Telegram downloads"). That makes download throughput and resume behavior a first-class migration risk, not just an API rename.

### Affected Areas
- `requirements.txt` — replace `pyrogram`/`tgcrypto` with `telethon`; review native dependency needs in Docker.
- `Dockerfile` — remove Pyrogram/TgCrypto assumptions; confirm Alpine build/runtime dependencies still cover Telethon.
- `scripts/auth.py` — rewrite interactive login to create a Telethon session and handle 2FA; avoid silently overwriting an incompatible Pyrogram session without backup or explicit re-auth.
- `app/telegram_client.py` — highest-impact module: lifecycle, session path, numeric peer resolution, `get_channel_info()`, `get_channel_messages()`, message-to-API mapping, thumbnail handling, and any adapter surface.
- `app/channels.py` — `auto_discover_channels()` imports `pyrogram.enums.ChatType` and must use Telethon dialog/entity types instead.
- `app/media.py` — current extractor expects Pyrogram media attributes (`file_name`, `file_size`, `mime_type`); Telethon commonly exposes metadata through `message.file` and/or different document/photo structures.
- `app/torznab/search.py` — uses `search_messages()`, `get_messages(chat_id, msg_id)`, Pyrogram message text/caption/date/media semantics, and paired-message lookup.
- `app/download.py` — fetches message by ID and relies on common media metadata to create synthetic torrents.
- `app/stream.py` — fallback file download uses `download_media(message, file_name=...)`; Telethon uses different `download_media()` argument naming.
- `app/transmission/downloader.py` — uses Pyrogram `stream_media(message, offset=chunk_offset)` with 1 MiB chunk resume semantics; Telethon needs an equivalent based on `iter_download()`/`download_media()` and byte offsets.
- `app/api_v2/router.py` — direct message fetch in `POST /api/v2/downloads` and imported helper behavior must remain stable for the frontend.
- `tests/conftest.py` — shared mock client, Pyrogram import workaround, and fixture method names need to reflect either the adapter surface or direct Telethon APIs.
- `tests/test_telegram_client.py`, `tests/torznab/test_search.py`, `tests/test_stream.py`, `tests/transmission/test_downloader.py`, API v2 channel/download tests — update mocks and assertions around message shape, history/search iteration, thumbnails, and streaming.
- `README.md`, `AGENTS.md`, `openspec/config.yaml`, existing specs mentioning Pyrogram — documentation/spec context must be updated in later phases.

### Approaches
1. **Thin compatibility adapter** — Replace the singleton with an app-owned Telegram gateway that exposes the current Pyrogram-shaped methods used by the application (`get_messages(chat_id, msg_id)`, `search_messages()`, `get_chat_history()`, `download_media()`, `stream_media()`), internally backed by Telethon.
   - Pros: smallest application diff; keeps Torznab/download/channel flows stable; tests can migrate incrementally; isolates Telethon message/media quirks in one place; safest path for real-search verification before commit.
   - Cons: adapter must emulate enough Pyrogram behavior carefully; risk of hiding Telethon-specific capabilities; thumbnail and streaming emulation may be non-trivial.
   - Effort: Medium

2. **Direct Telethon rewrite** — Replace every Pyrogram call site with Telethon APIs (`iter_messages(search=...)`, `get_messages(ids=...)`, `iter_download()`, direct entity/message handling).
   - Pros: no compatibility layer; code speaks Telethon directly; fewer conceptual translations long term.
   - Cons: broad diff across search, download, stream, channel browser, tests, and docs; higher chance of regressions before real verification; repeats Telethon message-shape logic in multiple modules.
   - Effort: High

3. **Hybrid gateway plus normalized domain objects** — Introduce a gateway that returns normalized app-level DTOs for search results, channel messages, media metadata, thumbnails, and downloads instead of exposing either library's raw message objects.
   - Pros: cleanest architecture; future Telegram library swaps become easier; reduces framework leakage.
   - Cons: larger refactor than needed for this migration; requires updating many callers and tests; more risk under the user's strict no-commit-until-real-searches-pass constraint.
   - Effort: High

### Recommendation
Use the thin compatibility adapter for the migration, then optionally clean toward normalized domain objects later. The current code already has a natural choke point (`app/telegram_client.py`) and the user's critical acceptance criterion is operational proof with real channels, not a broad architecture cleanup. Keeping the public app behavior stable while swapping the Telegram backend is the safest route.

Session strategy should be explicit: treat Pyrogram and Telethon sessions as incompatible, require a fresh Telethon authentication (or a clearly named Telethon session path) and preserve/backup the existing Pyrogram session for rollback. Do not rely on the existing `.session` file working across libraries.

Real-credential smoke verification should be planned as a manual post-implementation gate, not part of automated tests: authenticate with real `API_ID`, `API_HASH`, `PHONE`; start the service with real `channels.json`; run a Torznab or API v2 search against known real channels; verify at least one result maps to a real `chat_id:msg_id`; fetch its synthetic torrent; and optionally start a small download to prove `get_messages()` plus streaming works. Only after this succeeds should commits be allowed.

### Risks
- Existing Pyrogram `.session` files are not safe to assume compatible with Telethon; overwriting them would hurt rollback.
- Telethon download throughput may regress versus Pyrogram/TgCrypto; previous history says Pyrogram was chosen for faster downloads.
- `stream_media(offset=chunk_offset)` does not map 1:1 to Telethon; resume must preserve byte alignment and state semantics.
- Message/media attributes differ enough that search results, filename/size detection, thumbnails, sender names, topics, and web page text can regress silently.
- Numeric private channel IDs may require Telethon entity resolution/cache handling; dialog preload may still be needed.
- Flood-wait behavior and exceptions differ (`FloodWaitError.seconds`); existing semaphores may need Telethon-specific handling.
- Tests alone cannot satisfy the user's gate because current tests mock Telegram completely.
- No commits should be made until real searches in real channels with real credentials pass.

### Ready for Proposal
Yes — proceed to proposal/spec/design. The orchestrator should preserve the user's hard gate explicitly: implementation may run tests, but commits are blocked until a real-credential search smoke check passes against real Telegram channels.
