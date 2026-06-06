# Tasks: Channel View from Search

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 650-850 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 backend API → PR 2 frontend navigation/UI |
| Delivery strategy | ask-on-risk (ask-always preflight) |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Channel metadata/messages API | PR 1 | Backend tests, media filtering, auth/errors included. |
| 2 | Search-to-channel browser UI | PR 2 | Frontend API/types, card link, route tests/build included. |

## Phase 1: Backend RED Tests

- [x] 1.1 Add `tests/test_media.py` cases for document/video/audio/photo extraction and non-downloadable media omission.
- [x] 1.2 Add `tests/test_telegram_client.py` cases for `get_channel_messages()` pagination, filtering, `has_more`, and semaphore waiting.
- [x] 1.3 Add `tests/api_v2/test_channels.py` for `GET /channels/{chatId}` and `/messages`: 200, 401, 404, 422, 429, 502.
- [x] 1.4 Update `tests/conftest.py` mock Telegram client with async `get_chat_history()` and `get_chat()` fixtures.

## Phase 2: Backend GREEN/REFACTOR

- [x] 2.1 Extend `app/media.py` so `extract_media_info()` supports document, video, audio, and photo while excluding unsupported media.
- [x] 2.2 Add `_channel_messages_semaphore` and `get_channel_messages(chat_id, before=None, limit=20)` to `app/telegram_client.py`.
- [x] 2.3 Add channel metadata helper in `app/telegram_client.py` using `client.get_chat()` with clear disconnected/inaccessible errors.
- [x] 2.4 Wire `GET /api/v2/channels/{chatId}` and `/messages` in `app/api_v2/router.py`, validating known channels via `app/channels.py`.
- [x] 2.5 Run `python3 -m pytest tests/test_media.py tests/test_telegram_client.py tests/api_v2/test_channels.py` and refactor duplicated mapping code.

## Phase 3: Frontend RED Tests

- [x] 3.1 Add Vitest coverage for `frontend/src/lib/api.ts` channel URLs, `before`, `limit`, and error statuses.
- [x] 3.2 Add component tests for `SearchResultCard.svelte`: linked badge with `chatId`, unchanged non-link fallback without it.
- [x] 3.3 Add route tests for `/channels/[id]`: loading, empty, retryable error, pagination, and per-message download state.

## Phase 4: Frontend GREEN/REFACTOR

- [x] 4.1 Extend `frontend/src/lib/types.ts` with `ChannelInfo`, `ChannelMessage`, `ChannelMessagesResponse`, and `Channel.chatId`.
- [x] 4.2 Add `getChannelInfo()`, `getChannelMessages()`, and message download helper in `frontend/src/lib/api.ts`.
- [x] 4.3 Update `frontend/src/lib/components/SearchResultCard.svelte` to render channel badge as `/channels/{chatId}` when available.
- [x] 4.4 Update `frontend/src/routes/search/+page.svelte` channel mapping so cards receive `chatId` from API v2 channel data.
- [x] 4.5 Create `frontend/src/routes/channels/[id]/+page.svelte` with header, message list, cursor history, retry, and download actions.

## Phase 5: Verification

- [x] 5.1 Run `python3 -m pytest --cov=app --cov-report=term-missing --tb=short` and keep new backend coverage above 80%.
- [x] 5.2 Run `cd frontend && npm run test` and `cd frontend && npm run build`; fix only regressions in this change scope.

## Phase 6: Post-Verify Fixes

- [x] 6.1 Fix search page channel loading so configured settings refresh empty channel lists and stale stored channel lists missing `chatId`, preserving enabled state via `channelsStore.setChannels()`.

## Phase 7: Runtime Blocker Fixes

- [x] 7.1 Replace `iter_messages()` channel browsing with Pyrogram `get_chat_history()` while preserving `before` cursor, semaphore, filtering, lookahead, and pagination metadata.
- [x] 7.2 Update backend tests and shared Telegram fixture to mock `get_chat_history()` instead of `iter_messages()`.

## Phase 8: Exact Message and Message Content Remediation

- [x] 8.1 Add Strict TDD tests for search result links including exact `message` id and channel page `around` loading/highlight.
- [x] 8.2 Add backend Strict TDD tests for `around`, message `text`/`caption`, thumbnail URL, thumbnail endpoint, and full channel metadata in messages response.
- [x] 8.3 Implement `around` support using Pyrogram `get_messages()` plus `get_chat_history()` without `iter_messages()`.
- [x] 8.4 Extend channel message DTO and frontend rendering for captions/text and thumbnails without downloading full files.
- [x] 8.5 Run focused and broader backend/frontend verification.
