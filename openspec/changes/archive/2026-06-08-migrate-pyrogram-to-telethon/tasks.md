# Tasks: Migrate from Pyrogram to Telethon

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 900-1,400 |
| 400-line budget risk | Low against selected 1,000,000,000-line budget; exceeds default guard |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | single-pr |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Complete Telethon migration with tests, docs, and smoke gate | PR 1 | No commit until real-channel search gate passes |

## Phase 1: Dependency, Session, and Test Foundation

- [x] 1.1 RED: test Telethon session handling in `tests/` and `scripts/auth.py`; assert Pyrogram sessions are preserved.
- [x] 1.2 Replace `pyrogram`/`tgcrypto` with `telethon` in `requirements.txt` and adjust `Dockerfile` dependencies.
- [x] 1.3 Update `scripts/auth.py` to create Telethon sessions, support phone login/2FA, and preserve Pyrogram sessions.
- [x] 1.4 Remove Pyrogram-specific test import shims and define adapter-shaped `AsyncMock` fixtures in `tests/conftest.py`.

## Phase 2: Telegram Adapter Implementation

- [x] 2.1 RED: add `tests/test_telegram_client.py` coverage for lifecycle, cache, wrappers, flood waits, and stream offsets.
- [x] 2.2 Implement `TelegramAdapter` in `app/telegram_client.py` with required message, search, history, download, and stream methods.
- [x] 2.3 Add wrappers in `app/telegram_client.py` for text, caption, date, chat, sender/topic fields, media, thumbnails, and `empty`.
- [x] 2.4 Preserve 1 MiB resume semantics in `stream_media(message, offset=...)` using Telethon byte offsets.

## Phase 3: Application Compatibility

- [x] 3.1 RED: update search and paired-message tests for Torznab/API v2 result mapping in `tests/`.
- [x] 3.2 Adapt `app/media.py` to read wrapped Telethon media while preserving metadata contracts.
- [x] 3.3 Adapt `app/channels.py` dialog/channel detection without `pyrogram.enums.ChatType`; keep `channels.json` unchanged.
- [x] 3.4 Adjust `app/torznab/search.py` only where adapter exception/text behavior requires it.
- [x] 3.5 Verify `app/download.py`, `app/stream.py`, `app/transmission/downloader.py`, and `app/api_v2/router.py` fetch, torrent, stream, and resume paths.

## Phase 4: Automated Verification

- [x] 4.1 RED/GREEN: cover `/api/v2/channels/{chatId}/messages` pagination, 404, 429, 502, and max-limit validation.
- [x] 4.2 RED/GREEN: cover Torznab/API v2 search returning stable `chat_id:msg_id`, paired media lookup, and synthetic torrent fetchability.
- [x] 4.3 Run `python3 -m pytest --cov=app --cov-report=term-missing --tb=short`; fix regressions without real Telegram connections.

## Phase 5: Cleanup and Real-Credential Gate

- [x] 5.1 Update `README.md`, `AGENTS.md`, and `openspec/config.yaml` references from Pyrogram to Telethon, including session/auth instructions.
- [x] 5.2 Remove unused Pyrogram imports, config text, and mocks across `app/`, `scripts/`, and `tests/`.
- [x] 5.3 HARD GATE: before any commit, create/use a real Telethon session with real `API_ID`, `API_HASH`, `PHONE`, and configured real channels.
- [x] 5.4 HARD GATE: run real Torznab/API v2 searches; confirm one result maps to fetchable `chat_id:msg_id` and synthetic torrent.
- [x] 5.5 HARD GATE: if authentication, access, result mapping, or torrent fetch fails, do not commit; fix and repeat real-channel verification. Pass/no fix needed after successful real gate.
