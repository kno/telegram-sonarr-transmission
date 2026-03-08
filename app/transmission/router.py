import base64
import hmac
import json
import os
import uuid

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from app.config import settings
from app.transmission.state import get_downloads, get_downloads_snapshot
from app.transmission.websocket import get_ws_clients
from app.transmission import handlers

router = APIRouter()

# Session ID for CSRF protection (Transmission protocol requirement)
SESSION_ID = uuid.uuid4().hex[:48]


def _check_auth(request: Request):
    """Verify HTTP Basic Auth. Return error response if invalid."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            decoded = base64.b64decode(auth[6:]).decode()
            username, password = decoded.split(":", 1)
            if password != settings.TORZNAB_APIKEY:
                return JSONResponse(status_code=401, content={"result": "unauthorized"})
        except Exception:
            return JSONResponse(status_code=401, content={"result": "unauthorized"})
    return None


def _check_session(request: Request):
    """Verify X-Transmission-Session-Id header. Return error response if invalid."""
    client_session = request.headers.get("X-Transmission-Session-Id", "")
    if client_session != SESSION_ID:
        return JSONResponse(
            status_code=409,
            headers={"X-Transmission-Session-Id": SESSION_ID},
            content={"result": "error"},
        )
    return None


def _rpc_response(result: str, arguments: dict, tag=None):
    resp = {"result": result, "arguments": arguments}
    if tag is not None:
        resp["tag"] = tag
    return JSONResponse(
        content=resp,
        headers={"X-Transmission-Session-Id": SESSION_ID},
    )


@router.get("/transmission/rpc")
async def transmission_rpc_get(request: Request):
    """Handle GET requests — Sonarr uses this to verify the endpoint exists."""
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err
    return JSONResponse(
        status_code=409,
        headers={"X-Transmission-Session-Id": SESSION_ID},
        content={"result": "error"},
    )


@router.post("/transmission/rpc")
async def transmission_rpc(request: Request):
    auth_err = _check_auth(request)
    if auth_err:
        return auth_err

    err = _check_session(request)
    if err:
        return err

    body = await request.json()
    method = body.get("method", "")
    arguments = body.get("arguments", {})
    tag = body.get("tag")

    handler_map = {
        "session-get": handlers.session_get,
        "session-stats": handlers.session_stats,
        "torrent-add": handlers.torrent_add,
        "torrent-get": handlers.torrent_get,
        "torrent-remove": handlers.torrent_remove,
        "torrent-set": handlers.torrent_set,
        "torrent-start": handlers.torrent_start,
        "torrent-stop": handlers.torrent_stop,
    }

    handler = handler_map.get(method)
    if handler is None:
        return _rpc_response("method not recognized", {}, tag)

    result_args = await handler(arguments)
    return _rpc_response("success", result_args, tag)


@router.get("/transmission/files/{torrent_id}")
async def serve_download(torrent_id: int, request: Request, apikey: str = ""):
    """Serve a completed download file to the browser."""
    if apikey:
        if not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
    else:
        auth_err = _check_auth(request)
        if auth_err:
            return auth_err

    downloads = get_downloads()
    info = downloads.get(torrent_id)
    if not info:
        return JSONResponse(status_code=404, content={"error": "not found"})

    if not info.get("isFinished", False):
        return JSONResponse(status_code=400, content={"error": "download not complete"})

    file_path = os.path.join(info["downloadDir"], info["name"])
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "file not found on disk"})

    return FileResponse(
        path=file_path,
        filename=info["name"],
        media_type="application/octet-stream",
    )


@router.websocket("/ws/downloads")
async def ws_downloads(ws: WebSocket, apikey: str = ""):
    """WebSocket endpoint for live download progress updates."""
    if not apikey or not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
        await ws.close(code=4001, reason="unauthorized")
        return
    await ws.accept()
    clients = get_ws_clients()
    clients.add(ws)
    try:
        await ws.send_text(json.dumps({
            "type": "downloads",
            "downloads": get_downloads_snapshot(),
        }))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        clients.discard(ws)
