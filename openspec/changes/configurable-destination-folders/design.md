# Design: Configurable Destination Folders

## Technical Approach

Extend download state to track real file paths, add a `destinations.py` module (same JSON persistence pattern as `channels.py`), expose folder CRUD + file browsing + move actions via API v2, implement `torrent-set location` in the Transmission RPC handler, and fix `stream.py` to resolve files via state before falling back to directory scanning.

## Architecture Decisions

| Option | Tradeoff | Decision |
|--------|----------|----------|
| `destinations.py` vs. inline in router | Separation beats coupling; testable in isolation; mirrors `channels.py` precedent | New module, same pattern |
| File browser client-side (Node fs) vs. server-side | Docker backend has actual FS access; SvelteKit static build has none | Server-side `GET /api/v2/browse` |
| `torrent-set location`: all-or-nothing vs. partial success | Sonarr expects per-torrent success; partial avoids cascading failures | Per-torrent with individual errors |
| `session-get` report destinations | Prowlarr/Sonarr ignore this field for folder awareness | Skip — no consumer reads it |
| Stream resolve priority | `_file_path` > `downloadDir + name` > scan DOWNLOAD_DIR | State-first, scan fallback |

## Data Flow

```
Add destination:
  Settings page ──→ GET /api/v2/browse?path=...
                        ← dir listing
                    User picks dir, enters name
                    ──→ POST /api/v2/folders
                        → destinations.py validates (exists, r/w, no ..)
                        → saves to destinations.json
                        ← 201

Move download:
  Download page ──→ POST /api/v2/downloads/{id}/move {destination_path}
                      → resolves real path
                      → os.rename/shutil.move file on disk
                      → updates state.downloadDir + _file_path
                      → save_state() + broadcast_downloads()
                      ← 200

Sonarr torrent-set location:
  Sonarr ──→ POST /transmission/rpc {method: "torrent-set", location}
              → handlers.py: for each id:
                  if pending: update downloadDir only
                  if done: move file + update state + path
              ← {"result": "success"}

Stream after move:
  Client ──→ GET /api/stream?id=chat_id:msg_id
              → _find_cached_file()
                → search state for matching chat_id:msg_id
                → if _file_path exists → return it
                → else downloadDir + name → return it
                → else scan DOWNLOAD_DIR (old behavior)
              → serve file
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `app/destinations.py` | Create | Destination CRUD + file browser helper; JSON persistence at `DESTINATIONS_FILE` |
| `app/transmission/state.py` | Modify | Track `_file_path: str | None` per download; expose `find_by_chat_msg(chat_id, msg_id)` |
| `app/transmission/handlers.py` | Modify | Implement `torrent-set` with `location` arg; respect `download-dir` in `torrent-add` |
| `app/transmission/downloader.py` | Modify | After completion, set `_file_path` to actual dest path |
| `app/stream.py` | Modify | `_find_cached_file()` resolves via state first |
| `app/api_v2/router.py` | Modify | Add browse, folders CRUD, move, bulk-move endpoints |
| `app/config.py` | Modify | Add `DESTINATIONS_FILE: str = "/data/destinations.json"` |
| `frontend/src/lib/types.ts` | Modify | Add `Destination` type; `downloadDir` to `Download` |
| `frontend/src/lib/api.ts` | Modify | Add `fetchDestinations`, `createDestination`, `deleteDestination`, `browseFilesystem`, `moveDownload`, `bulkMoveDownloads` |
| `frontend/src/lib/stores.svelte.ts` | Modify | Add `destinationsStore` |
| `frontend/src/routes/settings/+page.svelte` | Modify | Add "Carpetas destino" section with file browser modal |
| `frontend/src/routes/downloads/+page.svelte` | Modify | "Mover a..." bulk action |
| `frontend/src/lib/components/DownloadRow.svelte` | Modify | "Mover a..." dropdown per row |

## Interfaces / Contracts

```python
# app/destinations.py — data model
@dataclass
class Destination:
    id: str            # uuid hex
    name: str          # user-facing label
    path: str          # absolute fs path
    created_at: float  # time.time()
```

```python
# app/transmission/state.py — new lookup
def find_by_chat_msg(chat_id: str, msg_id: int) -> dict | None
```

```typescript
// frontend new types
interface Destination {
	id: string;
	name: string;
	path: string;
}

// updated Download
interface Download {
	// ...existing fields...
	downloadDir?: string;
}
```

### API v2 Endpoints

| Method | Path | Body/Params | Response |
|--------|------|-------------|----------|
| GET | `/api/v2/folders` | — | `Destination[]` |
| POST | `/api/v2/folders` | `{name, path}` | `Destination` (201) |
| DELETE | `/api/v2/folders/{id}` | — | 204/409 (blocked) |
| GET | `/api/v2/browse` | `?path=/` | `{entries: [{name, isDir, size}]}` |
| POST | `/api/v2/downloads/{id}/move` | `{destination: str}` | `{status: "moved"}` |
| POST | `/api/v2/downloads/bulk-move` | `{ids: int[], destination: str}` | `{results: {id, status, error?}[]}` |

### Error codes

| Code | When |
|------|------|
| 400 | Invalid path, missing fields |
| 403 | Path traversal detected |
| 404 | Destination/download not found |
| 409 | Destination has active downloads |
| 500 | File move IO error |

## Testing Strategy

| Layer | What | Approach |
|-------|------|----------|
| Unit | `destinations.py` CRUD, path validation, browse | `tmp_path` fixture, mock `os.listdir`, test traversal rejection |
| Unit | `torrent-set location` handler | Mock `os.rename`, assert state mutations, test pending vs. completed paths |
| Unit | `_find_cached_file` after move | Seed mock state with `_file_path`, verify resolution; test fallback |
| Unit | File browser traversal blocking | Assert `..`, symlink escapes, non-existent dirs return 403/400 |
| Integration | Move via `async_client` | POST move, assert state change, assert file moved via mock |
| Frontend | Destination CRUD, file browser modal | Vitest component tests for modal + actions |

## Migration / Rollout

No migration required. Existing `downloads.json` entries missing `_file_path` will trigger the fallback scan path in `_find_cached_file`. `destinations.json` starts empty — `DOWNLOAD_DIR` acts as implicit default.

## Open Questions

- [ ] Should browse show dotfiles and hidden dirs by default? Decision: yes, with a boolean query param `?show_hidden=false`
