# Apply Progress: Migrate from Pyrogram to Telethon

## Status

Implementation complete through the real-credential hard gate. Completed dependency/session foundation, the Telethon compatibility adapter, channel auto-discovery migration, application compatibility coverage, automated verification coverage, cleanup, documentation/config references, focused corrective batches for adapter normalization, channel metadata normalization, result fetchability, and sanitized real Telethon/Torznab/API v2 verification. No commit was created.

## Real-Credential Gate Attempt: Passed

- Runtime prerequisites were verified without printing secret values: required credential/API-key settings were present, the verified Telethon session file existed, the legacy session file remained preserved, and the verified channels file contained 101 configured channels.
- Initial local startup using the project virtualenv failed because Telethon was not installed in that environment; `./.venv/bin/python -m pip install -r requirements.txt` installed the missing runtime dependency from the existing requirements file.
- Direct startup against the checked `data/torznab_session_telethon.session` file failed with `sqlite3.OperationalError: attempt to write a readonly database`, so the gate used a private temporary copy of that session under `/tmp/opencode/telethon-gate-session/` while preserving the original data session and legacy Pyrogram session files unchanged.
- Temporary app command shape: `SESSION_DIR=<temporary-session-copy-dir> SESSION_NAME=torznab_session CHANNELS_FILE=data/channels.json BASE_URL=http://127.0.0.1:<temp-port> DOWNLOAD_DIR=data/cache DESTINATIONS_FILE=data/destinations.json ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port <temp-port>`.
- Health check: `GET /health` returned HTTP 200.
- API v2 search command shape: `GET /api/v2/search?apikey=<redacted>&q=&limit=10` returned HTTP 200, `total=30`, `item_count=10`, and the first result had a stable redacted `chat_id:msg_id` shape (`chat_id` prefix `-100`, 13 chat-id digits, 6 message-id digits) with a download URL present.
- Synthetic torrent fetch command shape: `GET /api/download?id=<redacted-chat-id:msg-id>&apikey=<redacted>` returned HTTP 200, `content-type=application/x-bittorrent`, an attachment header, and readable torrent bytes.
- Torznab search command shape: `GET /api?t=search&q=&limit=10&apikey=<redacted>` returned HTTP 200, `content-type=application/xml`, `total=30`, `item_count=10`, and the first result had the same stable redacted `chat_id:msg_id` shape.
- Temporary app process was terminated after the gate.
- Tasks 5.3, 5.4, and 5.5 are complete; 5.5 is pass/no fix needed because authentication/startup via the copied session, real searches, result mapping, and synthetic torrent fetch succeeded.

## Historical Real-Credential Gate Attempt: Blocked Before Runtime Search

- Continuation retry (2026-06-08) re-ran the sanitized prerequisite check with the current `scripts.auth.resolve_session_paths(settings.SESSION_DIR, settings.SESSION_NAME)` signature.
- Result remained blocked: required runtime keys present, Telethon session file absent, local channels file absent, configured local channel count `0`.
- At that time, tasks 5.3, 5.4, and 5.5 remained unchecked because the real-credential gate could not run without those local runtime artifacts.

## Earlier Real-Credential Gate Attempt: Blocked Before Runtime Search

- Latest retry (2026-06-08) re-ran the sanitized prerequisite check after the user reported that the Telethon session had been initialized.
- Required runtime keys were still present through normal `.env`-backed runtime configuration; no secret values were printed.
- The configured Telethon session file was still absent at the runtime-resolved Telethon session path.
- The configured local channels file was still absent at the runtime-resolved `CHANNELS_FILE` path.
- Configured local channel count remained `0`.
- No local app process was started and no real Torznab/API v2 search was run because the hard gate prerequisites were not satisfied.
- No synthetic torrent fetch was attempted because there was no authenticated Telethon session file and no configured local channel list.
- Remediation required: create the Telethon session at the same `SESSION_DIR`/`SESSION_NAME` resolved by app runtime configuration and configure `CHANNELS_FILE` with accessible real channels, then rerun the real search and synthetic torrent gate.

## Previous Real-Credential Gate Attempt: Blocked Before Runtime Search

- Checked local runtime configuration through `.env` without printing secret values.
- Required runtime keys were present: `API_ID`, `API_HASH`, `PHONE`, `TORZNAB_APIKEY`, and `BASE_URL`.
- No Telethon session file was present at the configured Telethon session path.
- No configured local channels file was present at the configured `CHANNELS_FILE` path.
- No real Torznab/API v2 search was started because authenticating a new Telethon user session requires interactive login code input and may require two-step verification input.
- No synthetic torrent fetch was attempted because there was no authenticated session and no configured real channel list to search.
- Remediation required: run `docker compose --profile auth run --rm torznab-auth` from the workspace, complete Telegram login interactively, ensure the configured `CHANNELS_FILE` points to accessible real channels, then rerun the real search gate.

## Focused Corrective Batch: Channel Metadata Normalization

- Fixed `TelegramAdapter.get_chat()` so Telethon channel/supergroup entities with bare positive IDs are normalized to app-compatible Telegram peer IDs (`-100...`) before API v2 channel metadata is returned.
- Added focused regression tests for channel entity IDs, PeerChannel-style/supergroup IDs, and non-channel entities to preserve user/private entity IDs.
- Updated stale README test/coverage project-structure text to the current venv coverage result and documented the venv pytest runner caveat in `AGENTS.md` without replacing the general project command.
- No `tasks.md` checkbox was changed by this corrective batch because the related adapter/docs tasks were already marked complete and real-credential gate tasks remain pending.

## Focused Corrective Batch: Adapter Normalization

- Fixed Telethon dialog discovery so bare channel/supergroup entity IDs and `PeerChannel.channel_id` values are normalized to persisted Telegram peer IDs (`-100...`) before `channels.json` auto-discovery can save them.
- Fixed Telethon message media wrapping so non-file media shapes such as webpage previews are not exposed as downloadable `application/octet-stream` files with size `0`.
- Added regression tests for realistic Telethon channel IDs, PeerChannel-style IDs, webpage preview media, and a downloadable file-media control case.
- No `tasks.md` checkbox was changed by this corrective batch because the related adapter tasks were already marked complete and real-credential gate tasks remain pending.

## Apply Batch: Application Compatibility and Automated Coverage

- Added RED/GREEN coverage for wrapped Telethon file metadata in `app/media.py` and generalized media metadata extraction to read wrapper `.file` metadata while ignoring mock/unknown non-scalar attributes.
- Added API v2 search assertions for stable `chat_id:msg_id` mapping, explicit `chatId`/`msgId`, paired media lookup, and synthetic torrent download URL construction.
- Added Torznab HTTP coverage proving a paired text-result enclosure URL can be used to fetch a synthetic torrent.
- Verified download, stream fallback/range, Transmission resume, API v2 channel messages, and API v2 download lifecycle paths with focused tests.
- Cleaned stale Pyrogram wording in active guidance/test comments; remaining Pyrogram mentions in `scripts/auth.py` and `tests/test_auth_script.py` are intentional rollback/session-preservation contract checks.

## Completed Tasks

- [x] 1.1 RED: test Telethon session handling in `tests/` and `scripts/auth.py`; assert Pyrogram sessions are preserved.
- [x] 1.2 Replace `pyrogram`/`tgcrypto` with `telethon` in `requirements.txt` and adjust `Dockerfile` dependencies.
- [x] 1.3 Update `scripts/auth.py` to create Telethon sessions, support phone login/2FA, and preserve Pyrogram sessions.
- [x] 1.4 Remove Pyrogram-specific test import shims and define adapter-shaped `AsyncMock` fixtures in `tests/conftest.py`.
- [x] 2.1 RED: add `tests/test_telegram_client.py` coverage for lifecycle, cache, wrappers, flood waits, and stream offsets.
- [x] 2.2 Implement `TelegramAdapter` in `app/telegram_client.py` with required message, search, history, download, and stream methods.
- [x] 2.3 Add wrappers in `app/telegram_client.py` for text, caption, date, chat, sender/topic fields, media, thumbnails, and `empty`.
- [x] 2.4 Preserve 1 MiB resume semantics in `stream_media(message, offset=...)` using Telethon byte offsets.
- [x] 3.1 RED: update search and paired-message tests for Torznab/API v2 result mapping in `tests/`.
- [x] 3.2 Adapt `app/media.py` to read wrapped Telethon media while preserving metadata contracts.
- [x] 3.3 Adapt `app/channels.py` dialog/channel detection without `pyrogram.enums.ChatType`; keep `channels.json` unchanged.
- [x] 3.4 Adjust `app/torznab/search.py` only where adapter exception/text behavior requires it.
- [x] 3.5 Verify `app/download.py`, `app/stream.py`, `app/transmission/downloader.py`, and `app/api_v2/router.py` fetch, torrent, stream, and resume paths.
- [x] 4.1 RED/GREEN: cover `/api/v2/channels/{chatId}/messages` pagination, 404, 429, 502, and max-limit validation.
- [x] 4.2 RED/GREEN: cover Torznab/API v2 search returning stable `chat_id:msg_id`, paired media lookup, and synthetic torrent fetchability.
- [x] 4.3 Run `python3 -m pytest --cov=app --cov-report=term-missing --tb=short`; fix regressions without real Telegram connections.
- [x] 5.1 Update `README.md`, `AGENTS.md`, and `openspec/config.yaml` references from Pyrogram to Telethon, including session/auth instructions.
- [x] 5.2 Remove unused Pyrogram imports, config text, and mocks across `app/`, `scripts/`, and `tests/`.
- [x] 5.3 HARD GATE: before any commit, create/use a real Telethon session with real `API_ID`, `API_HASH`, `PHONE`, and configured real channels.
- [x] 5.4 HARD GATE: run real Torznab/API v2 searches; confirm one result maps to fetchable `chat_id:msg_id` and synthetic torrent.
- [x] 5.5 HARD GATE: if authentication, access, result mapping, or torrent fetch fails, do not commit; fix and repeat real-channel verification. Pass/no fix needed after successful real gate.

## TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 1.1 | `tests/test_auth_script.py`, `tests/test_telegram_client.py` | Unit | N/A for new auth tests; existing system runner unavailable (`python3 -m pytest`: no pytest) | ✅ Tests written first for Telethon suffix and Pyrogram session preservation | ✅ `.venv/bin/python -m pytest tests/test_auth_script.py tests/test_telegram_client.py tests/test_channels.py` passed | ✅ Session name + existing Pyrogram session + missing env cases | ✅ Extracted pure session path helpers |
| 1.2 | `tests/test_auth_script.py` | Unit/config | Same as 1.1 | ✅ Dependency/session tests written before dependency swap | ✅ Full backend suite passed in venv | ➖ Structural dependency change; behavior covered by session tests | ✅ Removed Pyrogram/TgCrypto runtime dependencies |
| 1.3 | `tests/test_auth_script.py` | Unit | Same as 1.1 | ✅ Auth helper tests written first | ✅ Focused suite passed | ✅ Missing env + session path behavior | ✅ Auth script split into testable helpers and interactive Telethon flow |
| 1.4 | `tests/conftest.py` consumers | Fixture/integration | Existing focused tests exercised shared fixture | ✅ Adapter-shaped fixture expectations written/updated first | ✅ Focused suite passed | ✅ Channel/search/downloader consumers covered by full suite | ✅ Removed Pyrogram event-loop import shim |
| 2.1 | `tests/test_telegram_client.py` | Unit | Existing `tests/test_telegram_client.py` covered lifecycle/channel behavior | ✅ Adapter tests written for lifecycle, wrappers, flood wait, stream offset | ✅ `tests/test_telegram_client.py`: 22 passed | ✅ Wrapper data + flood wait + offset cases | ✅ Flood wait mapping isolated in helper |
| 2.2 | `tests/test_telegram_client.py` | Unit | Same as 2.1 | ✅ Tests referenced `TelegramAdapter` before implementation | ✅ Focused/full suites passed | ✅ Search/history/get/download/stream methods covered by adapter and downstream suites | ✅ Kept app call surface stable |
| 2.3 | `tests/test_telegram_client.py` | Unit | Same as 2.1 | ✅ Wrapper assertions written first | ✅ Focused/full suites passed | ✅ Text/caption/media/sender/channel item cases | ✅ Added small wrapper classes |
| 2.2 corrective | `tests/test_telegram_client.py` | Unit | ✅ `./.venv/bin/python -m pytest tests/test_telegram_client.py tests/test_channels.py`: 38 passed before edits | ✅ Added failing tests for bare Telethon Channel IDs and PeerChannel-style IDs before production changes | ✅ `./.venv/bin/python -m pytest tests/test_telegram_client.py`: 26 passed | ✅ Entity ID and PeerChannel fallback cases | ✅ Extracted peer-id normalization helpers |
| 2.2 corrective metadata | `tests/test_telegram_client.py` | Unit | ✅ `./.venv/bin/python -m pytest tests/test_telegram_client.py`: 26 passed before edits | ✅ Added failing `get_chat()` tests for bare channel entity IDs and PeerChannel-style/supergroup IDs before production changes | ✅ `./.venv/bin/python -m pytest tests/test_telegram_client.py`: 29 passed | ✅ Channel entity + supergroup peer-style + non-channel preservation cases | ✅ Reused peer-id normalization helpers via `_entity_chat_id()` |
| 2.3 corrective | `tests/test_telegram_client.py` | Unit | ✅ Same safety net: 38 passed before edits | ✅ Added failing webpage-preview media test before production changes | ✅ `./.venv/bin/python -m pytest tests/test_telegram_client.py`: 26 passed | ✅ Webpage preview ignored plus downloadable file-media control case | ✅ Extracted file-metadata guard helper |
| 2.4 | `tests/test_telegram_client.py`, `tests/transmission/test_downloader.py` | Unit/integration | Existing downloader resume tests covered state semantics | ✅ Stream offset test written first | ✅ Focused/full suites passed | ✅ Offset 3 => byte offset `3 * 1MiB` | ✅ Shared `ONE_MIB` constant |
| 3.1 | `tests/api_v2/test_channels.py`, `tests/torznab/test_search.py` | Integration | ✅ 142 focused compatibility tests passed before edits | ✅ Added API v2 and Torznab paired-result fetchability tests before production changes | ✅ `./.venv/bin/python -m pytest tests/test_media.py tests/api_v2/test_channels.py tests/torznab/test_search.py`: 80 passed | ✅ Stable paired result + non-downloadable paired message cases | ✅ Kept search pairing centralized in `search_channels()` |
| 3.2 | `tests/test_media.py` | Unit | ✅ 142 focused compatibility tests passed before edits | ✅ Added wrapped Telethon `.file` metadata test before `app/media.py` change | ✅ Focused media/search/API tests passed | ✅ Direct media attrs + wrapped `.file` attrs + missing-field MagicMock case | ✅ Extracted typed metadata helper |
| 3.3 | `tests/test_channels.py` | Unit | Existing channel tests covered discovery/import/init | ✅ Tests updated away from `pyrogram.enums.ChatType` before app change | ✅ Focused/full suites passed | ✅ Channel, supergroup, private, group cases | ✅ Extracted `_is_channel_dialog()` |
| 3.4 | `tests/torznab/test_search.py` | Integration | ✅ 142 focused compatibility tests passed before edits | ✅ Paired-message and empty-marker tests cover adapter text/exception behavior | ✅ Focused/full suites passed | ✅ Error path + empty next message + stable result cases | ➖ No production change required in `app/torznab/search.py` |
| 3.5 | `tests/test_download_integration.py`, `tests/test_stream.py`, `tests/transmission/test_downloader.py`, `tests/api_v2/test_router.py`, `tests/api_v2/test_channels.py` | Integration | ✅ 142 focused compatibility tests passed before edits | ✅ Existing and new tests cover fetch, torrent, stream, resume, and API v2 paths | ✅ 176 focused compatibility tests passed | ✅ Download success/error, stream fallback/range, resume tmp alignment, API v2 search/download lifecycle | ➖ No extra production change required beyond API v2 search mapping |
| 4.1 | `tests/api_v2/test_channels.py` | Integration | ✅ 142 focused compatibility tests passed before edits | ✅ Endpoint tests cover pagination cursor, 404, 429, 502, and max-limit validation | ✅ Focused/full suites passed | ✅ Metadata included/skipped, before/around/topic, limit 422, backend errors | ➖ Coverage already matched spec; retained helper seam |
| 4.2 | `tests/api_v2/test_channels.py`, `tests/torznab/test_search.py` | Integration | ✅ 142 focused compatibility tests passed before edits | ✅ Added stable `chat_id:msg_id`, paired lookup, and torrent fetchability tests | ✅ Focused/full suites passed | ✅ API v2 mapping + Torznab enclosure-to-torrent | ✅ Added explicit API v2 download URL fields |
| 4.3 | Full backend suite | Verification | ✅ Focused suites green before full run | ✅ Full coverage command selected from venv per environment contract | ✅ Latest `./.venv/bin/python -m pytest --cov=app --cov-report=term-missing --tb=short`: 361 passed, 85% coverage | ✅ No real Telegram connections used | ➖ System `python3` remains unavailable for pytest; venv runner used |
| 5.1 | Documentation/config references | Docs/config | N/A docs | ✅ Existing migration tasks defined doc expectations first | ✅ Full backend suite unaffected | ➖ Docs-only | ✅ Updated README/AGENTS/OpenSpec context |
| 5.2 | `tests/torznab/test_search.py`, `CLAUDE.md` | Cleanup/docs | ✅ Focused suites green before cleanup | ✅ Grep identified stale active comments/docs before cleanup | ✅ Focused/full suites passed after cleanup | ✅ Active app/tests docs cleaned; intentional session-preservation Pyrogram references remain | ✅ Updated active guidance to Telethon adapter |
| 5.3 | Real credential/session gate | Operational hard gate | ✅ Verified prerequisite artifacts without printing secrets | N/A — no code change; operational gate uses existing session/auth implementation | ✅ Temporary app authenticated and reached HTTP 200 health using a Telethon session copy | N/A — single runtime authentication/session-use gate | ✅ Original data session and legacy session preserved |
| 5.4 | Real Torznab/API v2 search and torrent fetch gate | Operational hard gate | ✅ App health passed before searches | N/A — no code change; operational gate verifies existing search/download behavior | ✅ API v2 search, Torznab search, and synthetic torrent fetch returned HTTP 200 | ✅ JSON and XML search surfaces both returned stable redacted `chat_id:msg_id` result shapes | ✅ No production refactor performed |
| 5.5 | Failure remediation gate | Operational hard gate | ✅ Startup failures were isolated before retry | N/A — no code change; remediation was environment/runtime setup only | ✅ Gate passed after installing declared dependency and using a writable temporary session copy | ✅ Covered startup dependency failure, readonly session failure, search mapping, and torrent fetch | ✅ No fix needed in tracked code; no commit created |

## Test Summary

- **Total tests written/updated**: 5 new auth/adapter tests plus channel/conftest/test expectation updates; corrective batches added 7 adapter regression tests; application compatibility batch added 1 media test, 2 API v2 search tests, and 1 Torznab HTTP fetchability test.
- **Total tests passing**: 361 backend tests via `./.venv/bin/python -m pytest --cov=app --cov-report=term-missing --tb=short`.
- **Layers used**: Unit, integration, and operational real-credential smoke verification.
- **Approval tests**: Existing backend suite preserved behavior across search, download, stream, API v2, and Transmission flows.
- **Pure functions created**: `telethon_session_name()`, `resolve_session_paths()`, `missing_env_vars()`, `_telethon_session_name()`, `_string_attr()`, `_int_attr()`, `_raw_media_has_file_metadata()`, `_dialog_chat_id()`, `_entity_chat_id()`, `_is_channel_like_entity()`, `_is_telegram_peer_id()`, `_first_int_attr()`, `_first_peer_channel_id()`, `_to_telegram_peer_id()`, `_raise_timeout_for_flood_wait()`, `_is_channel_dialog()`, `_media_attr()`.

## Verification Commands

- `python3 - <<'PY' ... sanitized prerequisite check ... PY` → blocked: `/usr/bin/python3` has no `dotenv` module.
- `./.venv/bin/python - <<'PY' ... sanitized prerequisite check ... PY` → blocked first by `python-dotenv` `find_dotenv()` stdin assertion when no explicit path was passed.
- `./.venv/bin/python - <<'PY' ... load_dotenv('.env') sanitized prerequisite check ... PY` → required runtime keys present; Telethon session exists: false; channels file exists: false; configured channel count: 0.
- `python3 -m pytest tests/test_auth_script.py tests/test_telegram_client.py` → blocked: `/usr/bin/python3: No module named pytest`.
- `./.venv/bin/python -m pytest tests/test_auth_script.py tests/test_telegram_client.py tests/test_channels.py` → 40 passed.
- `./.venv/bin/python -m pytest tests/test_telegram_client.py` → 22 passed.
- `./.venv/bin/python -m pytest --cov=app --cov-report=term-missing --tb=short` → 350 passed, coverage 84%, 1 pre-existing Starlette/httpx deprecation warning.
- `python3 -m pytest --cov=app --cov-report=term-missing --tb=short` → blocked: `/usr/bin/python3: No module named pytest`.
- `./.venv/bin/python -m pytest tests/test_telegram_client.py tests/test_channels.py` → 38 passed before corrective edits.
- `./.venv/bin/python -m pytest tests/test_telegram_client.py` → RED: 3 failed (`Channel` entity ID normalization, `PeerChannel` fallback normalization, webpage preview media wrapping), 23 passed.
- `./.venv/bin/python -m pytest tests/test_telegram_client.py` → GREEN: 26 passed after corrective implementation.
- `./.venv/bin/python -m pytest tests/test_telegram_client.py tests/test_channels.py` → 42 passed after corrective implementation.
- `./.venv/bin/python -m pytest` → 354 passed, 1 pre-existing Starlette/httpx deprecation warning.
- `./.venv/bin/python -m pytest tests/test_media.py tests/torznab/test_search.py tests/api_v2/test_channels.py tests/test_download.py tests/test_stream.py tests/transmission/test_downloader.py` → 142 passed before application compatibility edits.
- `./.venv/bin/python -m pytest tests/test_media.py tests/api_v2/test_channels.py tests/torznab/test_search.py` → RED: 3 failed (wrapped Telethon media metadata, missing API v2 `chatId`/`msgId`/`downloadUrl`, Torznab test used an httpx response property incorrectly), 77 passed.
- `./.venv/bin/python -m pytest tests/test_media.py tests/api_v2/test_channels.py tests/torznab/test_search.py` → GREEN: 80 passed after media/API mapping implementation and test correction.
- `./.venv/bin/python -m pytest tests/test_media.py tests/torznab/test_search.py tests/api_v2/test_channels.py tests/api_v2/test_router.py tests/test_download.py tests/test_download_integration.py tests/test_stream.py tests/transmission/test_downloader.py` → 176 passed.
- `./.venv/bin/python -m pytest --cov=app --cov-report=term-missing --tb=short` → 358 passed, coverage 85%, 1 pre-existing Starlette/httpx deprecation warning.
- `./.venv/bin/python -m pytest tests/test_telegram_client.py` → 26 passed before channel metadata corrective edits.
- `./.venv/bin/python -m pytest tests/test_telegram_client.py` → RED: 2 failed (`get_chat()` bare channel entity ID normalization and PeerChannel-style/supergroup ID normalization), 27 passed.
- `./.venv/bin/python -m pytest tests/test_telegram_client.py` → GREEN: 29 passed after `get_chat()` metadata normalization implementation.
- `./.venv/bin/python -m pytest tests/test_telegram_client.py tests/test_channels.py` → 45 passed.
- `./.venv/bin/python -m pytest` → 361 passed, 1 pre-existing Starlette/httpx deprecation warning.
- `./.venv/bin/python -m pytest --cov=app --cov-report=term-missing --tb=short` → 361 passed, coverage 85%, 1 pre-existing Starlette/httpx deprecation warning.
- `./.venv/bin/python - <<'PY' ... sanitized runtime prerequisite check ... PY` → local `.env` loaded, required runtime keys present, but default host runtime paths pointed at `/data`; verified project artifacts were then checked explicitly at `data/` without printing contents.
- `./.venv/bin/python - <<'PY' ... sanitized verified artifact check ... PY` → Telethon session exists at verified path, legacy session preserved at verified path, channels file exists, configured channel count 101.
- `SESSION_DIR=data CHANNELS_FILE=data/channels.json BASE_URL=http://127.0.0.1:19117 DOWNLOAD_DIR=data/cache DESTINATIONS_FILE=data/destinations.json ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 19117` → startup failed: Telethon missing in local virtualenv.
- `./.venv/bin/python -m pip install -r requirements.txt` → installed missing declared Telethon runtime dependency in the local virtualenv.
- `SESSION_DIR=data CHANNELS_FILE=data/channels.json BASE_URL=http://127.0.0.1:19117 DOWNLOAD_DIR=data/cache DESTINATIONS_FILE=data/destinations.json ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 19117` → startup failed: `sqlite3.OperationalError: attempt to write a readonly database` on the checked session file.
- `./.venv/bin/python - <<'PY' ... copy verified Telethon session to /tmp/opencode/telethon-gate-session and chmod 0600 ... PY` → temporary writable session copy created; original data session preserved.
- `SESSION_DIR=/tmp/opencode/telethon-gate-session SESSION_NAME=torznab_session CHANNELS_FILE=data/channels.json BASE_URL=http://127.0.0.1:19117 DOWNLOAD_DIR=data/cache DESTINATIONS_FILE=data/destinations.json ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 19117` → health check HTTP 200.
- `GET /api/v2/search?apikey=<redacted>&q=&limit=10` → HTTP 200, `total=30`, `item_count=10`, first result stable redacted `chat_id:msg_id` shape, download URL present.
- `GET /api/download?id=<redacted-chat-id:msg-id>&apikey=<redacted>` → HTTP 200, `content-type=application/x-bittorrent`, attachment header present, torrent bytes readable.
- `GET /api?t=search&q=&limit=10&apikey=<redacted>` → HTTP 200, `content-type=application/xml`, `total=30`, `item_count=10`, first result stable redacted `chat_id:msg_id` shape.
- `./.venv/bin/python - <<'PY' ... terminate temporary uvicorn pid ... PY` → temporary app process terminated.

## Remaining Tasks

- None for apply.

## No-Commit and Real-Credential Gate Status

- No commit was created.
- Real credentials were used only through normal runtime configuration and the Telethon session; no secret values, session contents, phone/API data, API keys, or sensitive channel names were printed.
- Hard gate passed: a returned real result mapped to a stable redacted `chat_id:msg_id`, API v2 and Torznab searches succeeded, and the synthetic torrent endpoint was fetchable.
