# Apply Progress: Channel View from Search

## Status

- Change: `channel-view-from-search`
- Mode: Strict TDD
- Artifact store: OpenSpec
- PR boundary: single PR, maintainer-approved `size:exception`
- Tasks complete: 27/27
- Latest apply batch: exact search-result message navigation plus channel message text/caption/thumbnail remediation

## Completed Tasks

- [x] 1.1 Add `tests/test_media.py` cases for document/video/audio/photo extraction and non-downloadable media omission.
- [x] 1.2 Add `tests/test_telegram_client.py` cases for `get_channel_messages()` pagination, filtering, `has_more`, and semaphore waiting.
- [x] 1.3 Add `tests/api_v2/test_channels.py` for `GET /channels/{chatId}` and `/messages`: 200, 401, 404, 422, 429, 502.
- [x] 1.4 Update `tests/conftest.py` mock Telegram client with async `get_chat_history()` and `get_chat()` fixtures.
- [x] 2.1 Extend `app/media.py` so `extract_media_info()` supports document, video, audio, and photo while excluding unsupported media.
- [x] 2.2 Add `_channel_messages_semaphore` and `get_channel_messages(chat_id, before=None, limit=20)` to `app/telegram_client.py`.
- [x] 2.3 Add channel metadata helper in `app/telegram_client.py` using `client.get_chat()` with clear disconnected/inaccessible errors.
- [x] 2.4 Wire `GET /api/v2/channels/{chatId}` and `/messages` in `app/api_v2/router.py`, validating known channels via `app/channels.py`.
- [x] 2.5 Run focused backend tests and refactor duplicated mapping code.
- [x] 3.1 Add Vitest coverage for `frontend/src/lib/api.ts` channel URLs, `before`, `limit`, and error statuses.
- [x] 3.2 Add component tests for `SearchResultCard.svelte`: linked badge with `chatId`, unchanged non-link fallback without it.
- [x] 3.3 Add route tests for `/channels/[id]`: loading, empty, retryable error, pagination, and per-message download state.
- [x] 4.1 Extend `frontend/src/lib/types.ts` with `ChannelInfo`, `ChannelMessage`, `ChannelMessagesResponse`, and `Channel.chatId`.
- [x] 4.2 Add `getChannelInfo()`, `getChannelMessages()`, and message download helper in `frontend/src/lib/api.ts`.
- [x] 4.3 Update `frontend/src/lib/components/SearchResultCard.svelte` to render channel badge as `/channels/{chatId}` when available.
- [x] 4.4 Update `frontend/src/routes/search/+page.svelte` channel mapping so cards receive `chatId` from API v2 channel data.
- [x] 4.5 Create `frontend/src/routes/channels/[id]/+page.svelte` with header, message list, cursor history, retry, and download actions.
- [x] 5.1 Run backend coverage command and keep coverage above threshold.
- [x] 5.2 Run frontend test/build verification.
- [x] 6.1 Fix search page channel loading for empty or stale channel lists missing `chatId`.
- [x] 7.1 Replace `iter_messages()` channel browsing with Pyrogram `get_chat_history()` while preserving `before` cursor, semaphore, filtering, lookahead, and pagination metadata.
- [x] 7.2 Update backend tests and shared Telegram fixture to mock `get_chat_history()` instead of `iter_messages()`.
- [x] 8.1 Add Strict TDD tests for search result links including exact `message` id and channel page `around` loading/highlight.
- [x] 8.2 Add backend Strict TDD tests for `around`, message `text`/`caption`, thumbnail URL, thumbnail endpoint, and full channel metadata in messages response.
- [x] 8.3 Implement `around` support using Pyrogram `get_messages()` plus `get_chat_history()` without `iter_messages()`.
- [x] 8.4 Extend channel message DTO and frontend rendering for captions/text and thumbnails without downloading full files.
- [x] 8.5 Run focused and broader backend/frontend verification.

## Latest TDD Cycle Evidence

| Task | Test File | Layer | Safety Net | RED | GREEN | TRIANGULATE | REFACTOR |
|------|-----------|-------|------------|-----|-------|-------------|----------|
| 6.1 | `frontend/src/tests/search-page.test.ts` | Component/route | `npm run test -- src/tests/search-page.test.ts`: 2/2 passed before latest assertion refinement | Existing blocker test covered stale channels; refined setup to hydrate stale channels via `localStorage` + `channelsStore.load()` | `npm run test -- src/tests/search-page.test.ts`: 2/2 passed | Empty channel list + stale cached channel without `chatId`, enabled-state preservation, clickable link | Kept route predicate minimal |
| 7.1 | `tests/test_telegram_client.py` | Unit | `/tmp/opencode/tst-venv/bin/python -m pytest tests/test_telegram_client.py`: 11/11 passed before change | Updated tests to mock/assert `get_chat_history()`; RED: 3 failures because production still called `iter_messages()` | `/tmp/opencode/tst-venv/bin/python -m pytest tests/test_telegram_client.py`: 11/11 passed | Cursor call asserts `offset_id=before`; no-cursor asserts `offset_id=0`; semaphore still blocks third call | One-line production swap; no extra extraction needed |
| 7.2 | `tests/conftest.py` + backend suites | Fixture/unit | Shared fixture covered by full backend suite baseline from previous apply | Fixture updated from `iter_messages` to `get_chat_history` async generator after RED confirmed in unit tests | Focused backend: 20/20 passed; full backend: 332/332 passed | Router tests continue to use shared fixture with channel endpoints | Fixture mirrors actual Pyrogram method |
| 8.1 | `frontend/src/tests/components.test.ts`, `frontend/src/tests/channel-page.test.ts`, `frontend/src/tests/api-business.test.ts`, `frontend/src/tests/search-page.test.ts` | Component/API | `npm run test -- src/tests/channel-page.test.ts src/tests/components.test.ts src/tests/api-business.test.ts`: 127/127 passed | RED: 4 frontend failures for missing `?message`, `around`, caption/thumbnail rendering, and highlight | Focused frontend: 130/130 passed; full frontend: 182/182 passed | GUID with message id deep-links; legacy/non-matching guid keeps channel-only link; channel page uses `around` and highlights found message | Search-page legacy expectation updated to new exact-message contract |
| 8.2 | `tests/test_telegram_client.py`, `tests/api_v2/test_channels.py` | Unit/API | `/tmp/opencode/tst-venv/bin/python -m pytest tests/test_telegram_client.py tests/api_v2/test_channels.py`: 20/20 passed | RED: 7 backend failures for missing `around`, DTO fields, thumbnail helper/route, and full metadata in messages response | Focused backend: 25/25 passed; full backend: 337/337 passed, 86% coverage | Around loads exact message then older history; thumbnail downloads thumb object, not full media; messages response includes full metadata | Kept thumbnail detection minimal to Telegram `thumbs` objects |

## Latest Test Results

- `/tmp/opencode/tst-venv/bin/python -m pytest tests/test_telegram_client.py`: safety net 11 passed.
- `/tmp/opencode/tst-venv/bin/python -m pytest tests/test_telegram_client.py -q`: RED observed with 3 failures after tests were updated to expect `get_chat_history()`.
- `/tmp/opencode/tst-venv/bin/python -m pytest tests/test_telegram_client.py tests/api_v2/test_channels.py -q`: 20 passed.
- `npm run test -- src/tests/search-page.test.ts src/tests/components.test.ts`: 57 passed.
- `/tmp/opencode/tst-venv/bin/python -m pytest --cov=app --cov-report=term-missing --tb=short`: 332 passed, 86% coverage.
- `npm run test`: 179 passed.
- `/tmp/opencode/tst-venv/bin/python -m pytest tests/test_telegram_client.py tests/api_v2/test_channels.py`: safety net 20 passed.
- `npm run test -- src/tests/channel-page.test.ts src/tests/components.test.ts src/tests/api-business.test.ts`: safety net 127 passed.
- `/tmp/opencode/tst-venv/bin/python -m pytest tests/test_telegram_client.py tests/api_v2/test_channels.py -q`: RED observed with 7 failures after tests were added for `around`, DTO text/caption/thumbnail, thumbnail endpoint, and metadata contract.
- `npm run test -- src/tests/channel-page.test.ts src/tests/components.test.ts src/tests/api-business.test.ts`: RED observed with 4 failures after tests were added for `?message`, `around`, highlight, caption, and thumbnail rendering.
- `/tmp/opencode/tst-venv/bin/python -m pytest tests/test_telegram_client.py tests/api_v2/test_channels.py -q`: 25 passed.
- `npm run test -- src/tests/channel-page.test.ts src/tests/components.test.ts src/tests/api-business.test.ts`: 130 passed.
- `/tmp/opencode/tst-venv/bin/python -m pytest --cov=app --cov-report=term-missing --tb=short`: 337 passed, 86% coverage.
- `npm run test`: 182 passed.
- `npm run build`: passed; pre-existing Svelte a11y warnings remain in `frontend/src/routes/settings/+page.svelte`.

## Files Changed In Latest Batch

| File | Action | What Was Done |
|------|--------|---------------|
| `app/telegram_client.py` | Modified | Uses `client.get_chat_history(chat_id, limit=limit + 1, offset_id=before or 0)` for channel browsing instead of unsupported `iter_messages()`. |
| `tests/test_telegram_client.py` | Modified | Mocks/asserts `get_chat_history()` call semantics for cursor, no-cursor, pagination, filtering, and semaphore behavior. |
| `tests/conftest.py` | Modified | Shared mock Telegram client now exposes async `get_chat_history()` fixture. |
| `frontend/src/tests/search-page.test.ts` | Modified | Stale-channel test now hydrates old cached channels via `localStorage` and proves refresh makes channel badge clickable. |
| `openspec/changes/channel-view-from-search/tasks.md` | Modified | Added completed runtime blocker fix tasks 7.1 and 7.2. |
| `openspec/changes/channel-view-from-search/design.md` | Modified | Corrected channel browsing design references from `iter_messages()` to `get_chat_history()`. |
| `openspec/changes/channel-view-from-search/apply-progress.md` | Modified | Records latest Strict TDD evidence and cumulative completion status. |
| `app/telegram_client.py` | Modified | Adds `around` support, message text/caption/thumbnail URL DTO fields, and thumbnail-only download helper. |
| `app/api_v2/router.py` | Modified | Adds `around` query support, full channel metadata in messages responses, and message thumbnail endpoint. |
| `frontend/src/lib/api.ts` | Modified | Adds `around` support to `getChannelMessages()` with `before` preserved for older pagination. |
| `frontend/src/lib/types.ts` | Modified | Extends `ChannelMessage` with optional `text`, `caption`, and `thumbnail_url`. |
| `frontend/src/lib/components/SearchResultCard.svelte` | Modified | Builds channel links with `?message={msgId}` when `guid` has `chat_id:msg_id`. |
| `frontend/src/routes/channels/[id]/+page.svelte` | Modified | Reads `message` query param, loads with `around`, highlights found message, and renders captions/text/thumbnails. |
| `frontend/src/tests/*`, `tests/*` | Modified | Adds/remediates Strict TDD coverage for exact-message navigation and message content. |
| `openspec/changes/channel-view-from-search/specs/*`, `design.md`, `tasks.md` | Modified | Updates OpenSpec contracts and tasks for remediation behavior. |

## Deviations

None. The backend design artifact was corrected to the actual Pyrogram channel history method, and the implementation now follows that corrected design.

## Issues

None in this latest batch.
