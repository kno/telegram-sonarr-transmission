import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.channels import init_channels
from app.telegram_client import connect_client, disconnect_client
from app.torznab.router import router as torznab_router
from app.download import router as download_router
from app.stream import router as stream_router
from app.transmission import router as transmission_router, resume_downloads

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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "Telegram Torznab"}


# Serve SvelteKit static frontend (must be last, after all API routes)
_frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "build"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
else:

    @app.get("/")
    async def root():
        return {"status": "ok", "service": "Telegram Torznab"}
