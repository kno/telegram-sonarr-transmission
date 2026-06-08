# Proposal: Migrate from Pyrogram to Telethon

## Intent

Replace Pyrogram with Telethon while preserving current Torznab, API v2, download, stream, and channel browsing behavior. The driver is a library migration, not a product rewrite. Delivery is gated: no commits are allowed until real Telegram channel searches succeed with real credentials.

## Scope

### In Scope
- Replace Pyrogram runtime/auth dependencies with Telethon.
- Add a thin app-owned compatibility adapter in `app/telegram_client.py` for current caller expectations.
- Preserve search, paired-message lookup, synthetic torrent creation, channel browsing, thumbnail/media metadata, streaming, and resume semantics.
- Update Telegram mocks, docs/spec references, and session generation.
- Verify automated tests, then perform real-credential search smoke verification before any commit.

### Out of Scope
- Broad domain DTO refactor beyond what is needed for migration.
- Frontend UX changes unrelated to preserving existing behavior.
- Automated tests using real Telegram credentials.

## Capabilities

### New Capabilities
- `telegram-library-backend`: covers Telethon-backed lifecycle, auth/session creation, search/history/message fetch, media download, streaming, flood-wait handling, and real-credential smoke verification.

### Modified Capabilities
- `channel-messages-api`: replace Pyrogram-specific session/error assumptions with Telegram backend-neutral behavior.

## Approach

Use a thin compatibility adapter backed by Telethon, keeping existing call sites stable where practical. Treat Pyrogram and Telethon sessions as incompatible: create/use a Telethon-specific session path and preserve the old session for rollback. Required Telegram API capabilities: login with API ID/hash/phone/2FA, dialog/entity resolution, channel search, history pagination by message ID, direct message fetch, file metadata extraction, media download/streaming with offsets, thumbnails, and flood-wait errors.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `requirements.txt`, `Dockerfile` | Modified | Replace Pyrogram/TgCrypto with Telethon needs. |
| `scripts/auth.py` | Modified | Generate Telethon sessions safely. |
| `app/telegram_client.py` | Modified | Central adapter and lifecycle. |
| `app/channels.py`, `app/media.py`, `app/torznab/search.py` | Modified | Preserve discovery, metadata, and search behavior. |
| `app/download.py`, `app/stream.py`, `app/transmission/downloader.py`, `app/api_v2/router.py` | Modified | Preserve fetch, torrent, stream, and download flows. |
| `tests/`, `README.md`, `AGENTS.md`, `openspec/` | Modified | Update mocks and references. |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Session incompatibility | High | Use explicit Telethon session and keep Pyrogram session for rollback. |
| Download/resume regression | Med | Validate `iter_download()` offset behavior and smoke-download a small file. |
| Real channels fail despite mocked tests | High | Hard success gate: no commits before real searches pass. |
| Numeric channel/entity resolution differs | Med | Preload/cache dialogs and test configured channels. |

## Rollback Plan

Restore Pyrogram dependency/auth/client code and reuse the preserved Pyrogram session file. Because commits are blocked until real search verification passes, failed migration work can be discarded before entering history.

## Dependencies

- Valid real `API_ID`, `API_HASH`, `PHONE`, API key, and accessible real Telegram channels for smoke verification.
- Telethon-compatible session generation.

## Success Criteria

- [ ] All existing automated tests pass with Telethon-backed mocks.
- [ ] Real credentials authenticate successfully with a Telethon session.
- [ ] Real searches in real configured channels return valid results.
- [ ] At least one result maps to a fetchable `chat_id:msg_id` and synthetic torrent.
- [ ] No commits are created before the real-channel search gate passes.
