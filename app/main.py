import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.channels import init_channels
from app.telegram_client import connect_client, disconnect_client
from app.torznab.router import router as torznab_router
from app.download import router as download_router
from app.stream import router as stream_router
from app.transmission import router as transmission_router, resume_downloads
from app.api_v2 import router as api_v2_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Telegram Torznab server...")
    await connect_client()
    await init_channels()
    await resume_downloads()
    logger.info("Server ready.")
    yield
    logger.info("Shutting down...")
    await disconnect_client()


app = FastAPI(title="Telegram Torznab", lifespan=lifespan)
app.include_router(torznab_router)
app.include_router(download_router)
app.include_router(stream_router)
app.include_router(transmission_router)
app.include_router(api_v2_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Telegram Torznab"}


class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for unknown extensionless paths.

    SvelteKit with adapter-static + SPA mode emits a single index.html, so a
    hard reload on /downloads, /search, etc. would 404 without this. We only
    fall back for paths that look like client-side routes (no file extension)
    so that a missing /_app/*.js still surfaces a real 404.
    """

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not Path(path).suffix:
                return await super().get_response("index.html", scope)
            raise


# Serve SvelteKit static frontend (must be last, after all API routes)
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "build"
if _frontend_dir.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
else:

    @app.get("/")
    async def root():
        return {"status": "ok", "service": "Telegram Torznab"}
