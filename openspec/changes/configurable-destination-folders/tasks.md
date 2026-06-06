# Tasks: Configurable Destination Folders

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

| Field | Value |
|-------|-------|
| Estimated changed lines | 850-950 |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Delivery strategy | ask-on-risk |
| Chain strategy | **Pending — user decision** |

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Backend core: destinations module + state + stream fix | PR 1 | Tests included; base = main |
| 2 | Backend API + Transmission RPC integration | PR 2 | Depends on PR 1; base = main |
| 3 | Frontend: types, store, settings UI, downloads UI | PR 3 | Independent of PR 2; base = main |

### Delivery Strategy Notes

- **Estimated 850-950 lines** — well over 400-line budget
- **ask-on-risk**: user decides chain strategy before apply
- Options: `stacked-to-main` (fastest), `feature-branch-chain` (safer), or `size:exception` (single PR with maintainer OK)

## Phase 1: Backend Foundation

- [x] 1.1 `app/config.py` — add `DESTINATIONS_FILE: str = "/data/destinations.json"`
- [x] 1.2 `app/destinations.py` — new module: `Destination` dataclass, CRUD (create/list/rename/delete), JSON persistence (mirrors `channels.py`), file browser helper (`list_dir(path)` with traversal rejection)
- [x] 1.3 `app/transmission/state.py` — add `file_path: str | None` (persistent) to downloads; add `find_by_chat_msg(chat_id, msg_id) -> dict | None`
- [x] 1.4 `app/stream.py` — `_find_cached_file()` resolves via `find_by_chat_msg` state first, then `downloadDir + name`, then scan fallback
- [x] 1.5 `tests/test_destinations.py` — CRUD, path validation, traversal blocking, browse (tmp_path)
- [x] 1.6 `tests/transmission/test_state.py` — `find_by_chat_msg` + `file_path` serialization
- [x] 1.7 `tests/test_stream.py` — stream after move resolves via state

## Phase 2: Backend API & Transmission

- [ ] 2.1 `app/api_v2/router.py` — add: `GET /api/v2/folders`, `POST /api/v2/folders`, `DELETE /api/v2/folders/{id}`, `GET /api/v2/browse?path=`, `POST /api/v2/downloads/{id}/move`, `POST /api/v2/downloads/bulk-move`
- [ ] 2.2 `app/transmission/handlers.py` — `torrent-set`: implement `location` arg (pending = update downloadDir only; done = move file + update state + `_file_path`)
- [ ] 2.3 `app/transmission/handlers.py` — `torrent-add`: respect `download-dir` from args if matches configured destination, else fallback to DOWNLOAD_DIR
- [ ] 2.4 `app/transmission/downloader.py` — on completion, set `_file_path` to `os.path.join(downloadDir, name)`
- [ ] 2.5 `tests/api_v2/test_router.py` — folder CRUD, browse, move, bulk-move via async_client
- [ ] 2.6 `tests/transmission/test_handlers.py` — torrent-set location (pending vs done, nonexistent torrent), torrent-add download-dir matching
- [ ] 2.7 `tests/transmission/test_downloader.py` — `_file_path` set on completion

## Phase 3: Frontend

- [ ] 3.1 `frontend/src/lib/types.ts` — add `Destination { id, name, path }`, add `downloadDir?: string` to `Download`
- [ ] 3.2 `frontend/src/lib/api.ts` — add `fetchDestinations`, `createDestination`, `deleteDestination`, `browseFilesystem`, `moveDownload`, `bulkMoveDownloads`
- [ ] 3.3 `frontend/src/lib/stores.svelte.ts` — add `destinationsStore` (class with `$state`, localStorage cache, mirroring `channelsStore` pattern)
- [ ] 3.4 `frontend/src/routes/settings/+page.svelte` — add "Carpetas destino" section: destination list with create/delete, file browser modal (path input, dir listing, select)
- [ ] 3.5 `frontend/src/lib/components/DownloadRow.svelte` — add "Mover a..." dropdown (destinations list) for completed downloads
- [ ] 3.6 `frontend/src/routes/downloads/+page.svelte` — add bulk "Mover a..." action in selection toolbar
- [ ] 3.7 `frontend/src/tests/components.test.ts` — test destination CRUD UI, file browser modal, move action button
