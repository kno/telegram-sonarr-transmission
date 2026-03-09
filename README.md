# Telegram Torznab

A bridge that exposes Telegram channels as a [Torznab](https://torznab.github.io/spec-1.3-draft/)-compatible indexer and emulates a [Transmission](https://transmissionbt.com/) RPC download client. This allows **Sonarr**, **Radarr**, and **Prowlarr** to search and download media directly from Telegram channels — no real torrent tracker or client required.

## How It Works

```
Sonarr/Radarr                    Telegram Torznab                     Telegram
     |                                  |                                 |
     |--- search (Torznab XML) -------->|                                 |
     |                                  |--- search messages ------------>|
     |                                  |<-- messages with media ---------|
     |<-- RSS XML with results ---------|                                 |
     |                                  |                                 |
     |--- grab .torrent --------------->|                                 |
     |<-- synthetic .torrent -----------|                                 |
     |                                  |                                 |
     |--- torrent-add (Transmission)--->|                                 |
     |                                  |--- download file -------------->|
     |                                  |<-- file content ----------------|
     |--- torrent-get (poll status) --->|                                 |
     |<-- progress/completion ----------|                                 |
```

1. **Search** — Sonarr queries the Torznab `/api` endpoint. The server searches Telegram channels concurrently and returns results as Torznab RSS XML.
2. **Grab** — Sonarr requests the `.torrent` file. Instead of a real torrent, the server returns a synthetic `.torrent` containing `chat_id:msg_id` in its comment field.
3. **Download** — Sonarr sends the `.torrent` to the built-in Transmission RPC emulator. It extracts `chat_id:msg_id`, downloads the actual file from Telegram in the background, and reports progress back to Sonarr as if it were a real torrent transfer.

## Prerequisites

- **Telegram API credentials** — Obtain `API_ID` and `API_HASH` from [my.telegram.org](https://my.telegram.org)
- **Docker** and **Docker Compose**
- A Telegram account joined to the channels you want to index

## Setup

### 1. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

| Variable | Required | Description |
|---|---|---|
| `API_ID` | Yes | Telegram API ID from my.telegram.org |
| `API_HASH` | Yes | Telegram API hash from my.telegram.org |
| `PHONE` | Yes | Phone number associated with the Telegram account (e.g. `+1234567890`) |
| `TORZNAB_APIKEY` | Yes | API key that Sonarr/Prowlarr will use to authenticate requests |
| `BASE_URL` | Yes | URL where the server is reachable by Sonarr (e.g. `http://192.168.1.100:9117`) |
| `SESSION_NAME` | No | Telegram session file name (default: `torznab_session`) |
| `TORZNAB_PORT` | No | Host port to expose (default: `9117`) |
| `DOWNLOAD_DIR` | No | Directory for downloaded files (default: `./data/cache`) |
| `USER_CHANNELS_FILE` | No | Path to a `user_channels.json` file to import channels from |

### 2. Authenticate with Telegram

Before starting the server, you must create a Telegram session. This is an interactive process that requires you to enter a verification code (and optionally a 2FA password):

```bash
docker compose --profile auth run --rm torznab-auth
```

This will:
1. Connect to Telegram using your `API_ID`, `API_HASH`, and `PHONE`
2. Send a verification code to your Telegram app
3. Prompt you to enter the code
4. If 2FA is enabled, prompt for your password
5. Save the session file to `./data/torznab_session.session`

The session file persists in the `./data/` volume. You only need to run this once unless the session expires or is revoked.

### 3. Start the server

```bash
docker compose up -d
```

The server starts on port `9117` (or whatever `TORZNAB_PORT` is set to).

Verify it's running:
```bash
curl http://localhost:9117/
# {"status":"ok","service":"Telegram Torznab"}
```

## Channel Discovery

On first startup, if no `channels.json` exists, the server automatically discovers all Telegram channels your account is joined to and saves them to `./data/channels.json`. Each channel is assigned a unique category ID starting at 1000.

Alternatively, you can provide a `user_channels.json` file (from external tools) via the `USER_CHANNELS_FILE` env var to import a specific set of channels.

The channel list is stored in `./data/channels.json` and can be manually edited.

## Configuring Sonarr / Radarr

### Add as Indexer (via Prowlarr or directly)

| Setting | Value |
|---|---|
| Type | Torznab (Generic) |
| URL | `http://<server-ip>:9117` |
| API Path | `/api` |
| API Key | Your `TORZNAB_APIKEY` value |
| Categories | 5000 (TV), 2000 (Movies), or specific channel IDs |

### Add as Download Client

| Setting | Value |
|---|---|
| Type | Transmission |
| Host | `<server-ip>` |
| Port | `9117` |
| URL Base | `/transmission` |
| Username | anything |
| Password | Your `TORZNAB_APIKEY` value |

The Transmission emulator uses the API key as the password for HTTP Basic auth. The username field can be any value.

## API Endpoints

### Torznab

- `GET /api?t=caps` — Returns indexer capabilities (no auth required)
- `GET /api?t=search&q=...&apikey=...` — Free-text search
- `GET /api?t=tvsearch&q=...&season=1&ep=2&apikey=...` — TV search with season/episode filtering
- `GET /api?t=movie&q=...&apikey=...` — Movie search

Supports `cat` (comma-separated category IDs), `offset`, and `limit` parameters.

### Download & Stream

- `GET /api/download?id=<chat_id>:<msg_id>&apikey=...` — Returns a synthetic `.torrent` file
- `GET /api/stream?id=<chat_id>:<msg_id>&apikey=...` — Streams the actual file (with HTTP Range support)

### Transmission RPC

- `POST /transmission/rpc` — JSON-RPC endpoint supporting `session-get`, `session-stats`, `torrent-add`, `torrent-get`, `torrent-remove`, `torrent-set`

Uses Transmission's CSRF protection protocol (`X-Transmission-Session-Id` header).

## Web UI

The project includes a built-in web interface for managing searches, downloads, and channels directly from the browser — no Sonarr/Radarr required for basic use.

Access it at `http://<server-ip>:9117/` once the server is running.

### Pages

- **Dashboard** (`/`) — Overview with download stats, active transfer count, download speed, and quick actions.
- **Search** (`/search`) — Search across Telegram channels with filters for season/episode and channel selection. Results can be sent to download directly.
- **Downloads** (`/downloads`) — Real-time download manager with live progress via WebSocket. Supports pause, resume, and delete actions.
- **Channels** (`/channels`) — Enable/disable Telegram channels for search. Filter by name, bulk select/deselect.
- **Settings** (`/settings`) — Configure API key and backend URL. Includes a connection test button.

### Features

- Dark/light theme with system preference detection
- Responsive design with mobile support
- Real-time download progress via WebSocket (`/ws/downloads`)
- Spanish-language UI
- No server-side rendering required — static SPA served by FastAPI

### Frontend Development

The frontend is a SvelteKit 2 app with Svelte 5, Tailwind CSS 4, and TypeScript.

```bash
cd frontend
npm install
npm run dev     # Dev server with HMR (proxies API to :9117)
npm run build   # Build static files to frontend/build/
```

The production build is served by FastAPI from `frontend/build/`. No Node.js is needed at runtime.

## Development

### Run locally (without Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 9117 --reload
```

Requires a valid `.env` file and an existing session file in the configured `SESSION_DIR`.

### Project Structure

```
app/
  main.py              # FastAPI app, lifespan (connects Telegram on startup)
  config.py            # pydantic-settings configuration
  telegram_client.py   # Singleton Telethon client
  channels.py          # Channel registry (auto-discovery, JSON persistence)
  download.py          # /api/download — synthetic .torrent generation
  stream.py            # /api/stream — file serving with Range support
  transmission.py      # /transmission/rpc — Transmission RPC emulator
  torznab/
    router.py          # /api endpoint (Torznab protocol)
    search.py          # Search logic across Telegram channels
    caps.py            # Torznab capabilities XML
    errors.py          # Torznab error responses
frontend/
  src/
    lib/
      api.ts           # Backend API calls (Torznab, Transmission RPC, WebSocket)
      stores.svelte.ts # Reactive state (settings, channels, theme)
      types.ts         # TypeScript interfaces
      components/      # Navbar, SearchResultCard, DownloadRow, ProgressBar, ThemeToggle
    routes/            # SvelteKit file-based routing (/, /search, /downloads, /channels, /settings)
  build/               # Pre-built static output served by FastAPI
scripts/
  auth.py              # Interactive Telegram authentication
```

## Notes

- Download state is kept in memory and **not persisted** across server restarts. Active downloads will be lost if the server is restarted.
- Telegram API has rate limits. Searches are throttled to 3 concurrent channel queries to avoid flood waits.
- Downloaded files are cached on disk (`DOWNLOAD_DIR`). The cache is not automatically cleaned — manage disk space manually.
- The `.torrent` files are synthetic and cannot be used with real BitTorrent clients.
