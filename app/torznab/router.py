import hmac

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.config import settings
from app.torznab.caps import build_caps_response
from app.torznab.errors import torznab_error
from app.torznab.search import do_search

router = APIRouter()


@router.get("/api")
async def torznab_api(
    t: str = Query(..., description="Function type"),
    q: str | None = Query(None, description="Search query"),
    cat: str | None = Query(None, description="Category IDs (comma-separated)"),
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1),
    apikey: str | None = Query(None),
    # Accept but ignore other Torznab params for compatibility
    season: str | None = Query(None),
    ep: str | None = Query(None),
    imdbid: str | None = Query(None),
    tvdbid: str | None = Query(None),
    extended: int | None = Query(None),
    attrs: str | None = Query(None),
) -> Response:
    # caps doesn't require auth
    if t == "caps":
        return build_caps_response()

    # All other functions require apikey
    if not apikey or not hmac.compare_digest(apikey, settings.TORZNAB_APIKEY):
        return torznab_error(100)

    effective_limit = min(limit or settings.DEFAULT_LIMIT, settings.MAX_LIMIT)

    if t in ("search", "tvsearch", "movie", "music", "book"):
        return await do_search(q, cat, offset, effective_limit, season=season, ep=ep)

    return torznab_error(202)
