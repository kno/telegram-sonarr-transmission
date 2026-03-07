import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.channels import init_channels
from app.telegram_client import connect_client, disconnect_client
from app.torznab.router import router as torznab_router
from app.download import router as download_router
from app.stream import router as stream_router
from app.transmission import router as transmission_router

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
    logger.info("Server ready.")
    yield
    logger.info("Shutting down...")
    await disconnect_client()


app = FastAPI(title="Telegram Torznab", lifespan=lifespan)
app.include_router(torznab_router)
app.include_router(download_router)
app.include_router(stream_router)
app.include_router(transmission_router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "Telegram Torznab"}
