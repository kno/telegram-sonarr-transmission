# Proposal: Configurable Destination Folders

## Intent

All downloads currently go to a single hardcoded `/data/cache` dir. Users need to organize by media type, series, or priority — with the ability to move completed and pending files between configurable folders. This is a direct user request from the SDD onboarding.

## Scope

### In Scope
- Destination folder CRUD via a file browser UI (Settings page)
- Manual "Move to…" action per download (single + bulk from downloads page)
- `torrent-set location` implementation for Sonarr/Radarr compatibility
- `/api/stream` works after a move — looks up real path from download state
- Persistence in `destinations.json` + `downloads.json` per-download path updates

### Out of Scope
- Auto-organization rules or folder strategies
- Bulk reassignment (e.g. "move all Series X")
- Deleting a folder that still has active downloads
- Symlinks, file watchers, or FS event monitors

## Capabilities

### New
- `destinations`: CRUD of destination folders with server-side file browser

### Modified
- None (no existing openspec/specs/)

## Approach

1. **Backend**: New `app/destinations.py` (JSON persistence, same pattern as `channels.py`). File browser endpoint under API v2 (`GET /api/v2/browse?path=...`). Move endpoint updates download state, moves file on disk, updates `downloadDir` and file path.
2. **Stream fix**: `_find_cached_file()` looks up download state by `chat_id:msg_id` first, falls back to scanning `DOWNLOAD_DIR`.
3. **torrent-set**: Implement `download-dir` in handlers — update `downloadDir`, move file, save state.
4. **Frontend**: File browser modal component, destination list in Settings, "Mover a…" dropdown in DownloadRow.

## Affected Areas

| Area | Impact | Key Change |
|------|--------|------------|
| `app/destinations.py` | New | JSON-persisted destinations + file browser |
| `app/transmission/handlers.py` | Modified | `torrent-set location` moves file + updates state |
| `app/stream.py` | Modified | `_find_cached_file()` reads real path from state |
| `app/transmission/state.py` | Modified | Track real `_file_path` per download |
| `app/transmission/downloader.py` | Modified | Use configured destination dir on download |
| `app/api_v2/router.py` | Modified | New browse + move endpoints |
| `app/config.py` | Modified | Add `DESTINATIONS_FILE` setting |
| `frontend/src/routes/settings/` | Modified | Destination manager + file browser |
| `frontend/src/routes/downloads/` | Modified | "Mover a…" action in row toolbar |
| `frontend/src/lib/api.ts` | Modified | Browse + move API calls |
| `frontend/src/lib/types.ts` | Modified | Destination type + download `downloadDir` |

## Edge Cases

| Edge Case | Handling |
|-----------|----------|
| Path traversal | Reject `..` and paths outside allowed roots |
| Move file being streamed | Existing handle continues; new stream from new path |
| Move to same folder | No-op, return success |
| Docker volume restrictions | File browser only shows mounted volumes |
| Delete destination with downloads | Block deletion until downloads are moved |
| Empty destination list | `DOWNLOAD_DIR` behaves as implicit default |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Path traversal via browse API | Med | Server-side validation, reject `..` and symlink escapes |
| Stream breakage after move | Low | State-based path lookup, not dir scanning |
| Docker user mismatch (file perms) | Low | Document volume ownership requirements |

## Rollback Plan

Version-control revert: restore `app/stream.py`, revert `torrent-set` to `return {}`, delete `destinations.py`, revert frontend. Existing downloads stay at their current paths. `destinations.json` can be removed manually.

## Dependencies

- Read access to the filesystem paths the user intends to browse
- Docker volume mounts for non-default destination paths

## Success Criteria

- [ ] User browses server FS from Settings, adds 2+ destinations
- [ ] User moves a completed download → file physically moves, stream still works
- [ ] User moves a pending download → after completion, file lands in new folder
- [ ] Sonarr's `torrent-set location` invokes move + state update
- [ ] `destinations.json` persists and survives restart
- [ ] 196+ existing tests pass + new tests for browse, move, stream fix
