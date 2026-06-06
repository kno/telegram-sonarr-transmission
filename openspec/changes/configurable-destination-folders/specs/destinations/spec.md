# Destinations Specification

## Purpose

Define how users configure server-side destination folders, browse the filesystem, move downloads between folders, and how Sonarr/Radarr integration (torrent-set location, torrent-add download-dir) interacts with destinations.

## Requirements

### Requirement: Destination CRUD

The system MUST support creating, listing, renaming, and deleting destination folders. Each destination stores a name and filesystem path. Paths containing `..` MUST be rejected. Deleting a destination MUST be blocked if any active download targets it.

#### Scenario: Create destination
- GIVEN a valid directory /data/tv is browsed and readable
- WHEN the user saves it as destination "Series" via the settings UI
- THEN the destination is persisted to `destinations.json` with name and path

#### Scenario: Delete blocked by active downloads
- GIVEN destination /data/tv has 2 active downloads
- WHEN the user attempts to delete it
- THEN the operation is rejected with an error listing the blocking downloads

### Requirement: File Browser

The system MUST expose `GET /api/v2/browse?path=`. It MUST return directory entries (name, type, path) at that path. Root defaults to `/`. `..` MUST be rejected. Permission errors MUST return an empty entries list with an error key.

#### Scenario: Browse subdirectory
- GIVEN /data exists and is readable
- WHEN GET /api/v2/browse?path=/data is called
- THEN response contains entries with name, type, and path fields

#### Scenario: Permission denied
- GIVEN /root is not readable by the container user
- WHEN GET /api/v2/browse?path=/root is called
- THEN entries is empty and an error key describes the failure

### Requirement: Move Download

Completed downloads MUST be physically moved on disk and state updated. Pending downloads MUST update only `downloadDir` — the file lands there when downloaded. Moving to the same folder MUST be a no-op. On move failure (permission, disk full, missing source) the state MUST NOT be updated.

#### Scenario: Move completed download
- GIVEN a completed download has file at /data/cache/file.mkv
- WHEN the user moves it to destination /data/tv
- THEN the file is at /data/tv/file.mkv and state reflects new downloadDir

#### Scenario: Move pending download
- GIVEN a download is pending (not yet started)
- WHEN the user moves it to /data/tv
- THEN only downloadDir is updated and the file lands at /data/tv/ upon completion

### Requirement: Bulk Move

The system SHOULD support moving multiple downloads to a destination in one action. Failures MUST NOT roll back successes. The response MUST report which downloads succeeded and which failed.

#### Scenario: Partial success
- GIVEN 3 downloads: 2 completed, 1 with a missing source file
- WHEN bulk move to /data/tv is requested
- THEN 2 succeed, 1 is reported as failed, and the failed download's state is unchanged

### Requirement: Stream After Move

`_find_cached_file()` MUST look up the real file path from download state by `chat_id:msg_id` before falling back to scanning `DOWNLOAD_DIR`.

#### Scenario: Stream serves from new location
- GIVEN a file was moved from /data/cache to /data/tv
- WHEN /api/stream is requested for that download
- THEN the file is served from /data/tv/file.mkv

### Requirement: torrent-set location

The Transmission RPC `torrent-set` MUST support the `location` field to move a download's file and update state. It SHALL return success/failure per Transmission spec.

#### Scenario: Valid torrent-set location
- GIVEN a completed download with hash H at /data/cache
- WHEN torrent-set is called with {"hash": H, "location": "/data/tv"}
- THEN the file moves to /data/tv and state downloadDir is updated

#### Scenario: Non-existent torrent
- GIVEN a hash that does not exist in state
- WHEN torrent-set location is called
- THEN response indicates failure and no files are moved

### Requirement: torrent-add download-dir

When `torrent-add` receives a `download-dir` field, the system MUST use it if it matches a configured destination. Otherwise DOWNLOAD_DIR SHALL be the fallback.

#### Scenario: Matches configured destination
- GIVEN /data/tv is a configured destination
- WHEN torrent-add is called with download-dir=/data/tv
- THEN the download's downloadDir is set to /data/tv

#### Scenario: Unknown path falls back
- GIVEN /data/movies is NOT a configured destination
- WHEN torrent-add is called with download-dir=/data/movies
- THEN downloadDir uses DOWNLOAD_DIR and the unknown path is ignored
