import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from typing import Optional
from urllib.parse import quote

from fastapi.responses import Response

from app.channels import get_all_channels, get_channel_by_category, get_category_by_chat
from app.config import settings
from app.telegram_client import get_client

logger = logging.getLogger(__name__)

TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
NEWZNAB_NS = "http://www.newznab.com/DTD/2010/feeds/attributes/"


def _extract_media_info(message) -> Optional[dict]:
    """Extract filename, size, mime_type from a message with media."""
    if not message.media:
        return None
    doc = getattr(message.media, "document", None)
    if not doc:
        return None

    info = {
        "size": doc.size or 0,
        "mime_type": doc.mime_type or "application/octet-stream",
        "filename": None,
    }
    for attr in doc.attributes:
        if hasattr(attr, "file_name"):
            info["filename"] = attr.file_name
    return info


def _build_link(entity, message_id: int) -> str:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    return f"https://t.me/c/{entity.id}/{message_id}"


async def _search_channel(chat_id: str, query: str, limit: int) -> list[dict]:
    """Search a single channel, returning items with media."""
    client = get_client()
    items = []
    try:
        entity = await client.get_entity(int(chat_id))
        async for message in client.iter_messages(entity, search=query, limit=limit):
            media_info = _extract_media_info(message)
            if not media_info:
                continue

            title = media_info["filename"] or (message.text or "Unknown")[:200]
            link = _build_link(entity, message.id)
            ch_mapping = get_category_by_chat(chat_id)
            cat_id = ch_mapping["category_id"] if ch_mapping else 0

            items.append({
                "title": title,
                "guid": f"{chat_id}:{message.id}",
                "link": link,
                "chat_id": chat_id,
                "msg_id": message.id,
                "pub_date": message.date,
                "size": media_info["size"],
                "category_id": cat_id,
                "description": (message.text or "")[:500],
            })
    except Exception as e:
        logger.error("Error searching channel %s: %s", chat_id, e)
    return items


def _filter_by_season_ep(items: list[dict], season: str | None, ep: str | None) -> list[dict]:
    """Filter items by season/episode number matching common naming patterns."""
    filtered = []
    s_num = int(season) if season else None
    e_num = int(ep) if ep else None

    for item in items:
        title = item["title"]
        # Match patterns: S02E02, 2x02, S02, season 2, etc.
        if s_num is not None and e_num is not None:
            # S02E02 or S2E2
            if re.search(rf'S0*{s_num}E0*{e_num}\b', title, re.IGNORECASE):
                filtered.append(item)
                continue
            # 2x02 or 02x02
            if re.search(rf'\b0*{s_num}x0*{e_num}\b', title, re.IGNORECASE):
                filtered.append(item)
                continue
        elif s_num is not None:
            if re.search(rf'S0*{s_num}(?:E\d|[\s._-])', title, re.IGNORECASE):
                filtered.append(item)
                continue
            if re.search(rf'\b0*{s_num}x\d', title, re.IGNORECASE):
                filtered.append(item)
                continue

    return filtered


_search_semaphore = asyncio.Semaphore(3)


async def _search_channel_throttled(chat_id: str, query: str, limit: int) -> list[dict]:
    """Search with concurrency limit to avoid Telegram flood waits."""
    async with _search_semaphore:
        return await _search_channel(chat_id, query, limit)


async def do_search(
    query: str | None,
    cat: str | None,
    offset: int,
    limit: int,
    season: str | None = None,
    ep: str | None = None,
) -> Response:
    """Execute search across channels and return Torznab RSS XML."""
    # Resolve target channels
    if cat:
        try:
            cat_ids = [int(c.strip()) for c in cat.split(",") if c.strip()]
        except ValueError:
            from app.torznab.errors import torznab_error
            return torznab_error(201, "Invalid category ID")
        channels = [
            ch for cid in cat_ids
            if (ch := get_channel_by_category(cid)) is not None
        ]
        # If standard Newznab categories (5000+) didn't match any channel,
        # fall back to all channels so Sonarr/Radarr searches still work
        if not channels:
            channels = get_all_channels()
    else:
        channels = get_all_channels()

    if not channels:
        return _build_rss_response([], 0, offset)

    # Telegram search is phrase-based, so long multi-word queries often fail
    # when channels use translated/abbreviated names. Use the first significant
    # word (typically the main title) for broader matching.
    # Season/episode filtering is done post-search on filenames.
    raw_query = query or ""
    words = raw_query.split()
    # Use first word if query has 3+ words (likely a full title); otherwise use as-is
    search_query = words[0] if len(words) >= 3 and words[0] else raw_query

    # Without a query, limit to first 5 channels to avoid flood waits
    # (Sonarr test sends t=tvsearch without q)
    if not search_query:
        channels = channels[:5]

    per_channel = max(limit // len(channels), 10) if channels else limit

    # Search channels with throttling to avoid Telegram flood waits
    tasks = [
        _search_channel_throttled(ch["chat_id"], search_query, per_channel)
        for ch in channels
    ]
    results = await asyncio.gather(*tasks)

    # Flatten and sort by date descending
    all_items = [item for sublist in results for item in sublist]

    # Post-filter by season/episode if provided
    if season or ep:
        all_items = _filter_by_season_ep(all_items, season, ep)

    all_items.sort(key=lambda x: x["pub_date"], reverse=True)

    total = len(all_items)
    paginated = all_items[offset:offset + limit]

    return _build_rss_response(paginated, total, offset)


def _build_rss_response(items: list[dict], total: int, offset: int = 0) -> Response:
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")
    rss.set("xmlns:torznab", TORZNAB_NS)
    rss.set("xmlns:newznab", NEWZNAB_NS)

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "Telegram Torznab"
    ET.SubElement(channel, "description").text = "Telegram channel indexer via Torznab"
    ET.SubElement(channel, "link").text = settings.BASE_URL

    resp = ET.SubElement(channel, f"{{{NEWZNAB_NS}}}response")
    resp.set("offset", str(offset))
    resp.set("total", str(total))

    for item_data in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = item_data["title"]
        ET.SubElement(item, "guid").text = item_data["guid"]
        ET.SubElement(item, "link").text = item_data["link"]
        ET.SubElement(item, "comments").text = item_data["link"]

        if item_data["pub_date"]:
            ET.SubElement(item, "pubDate").text = format_datetime(item_data["pub_date"])

        ET.SubElement(item, "size").text = str(item_data["size"])
        ET.SubElement(item, "description").text = item_data["description"]

        # Download URL (returns .torrent with webseed)
        dl_id = quote(item_data["guid"], safe="")
        dl_url = (
            f"{settings.BASE_URL}/api/download"
            f"?id={dl_id}&apikey={settings.TORZNAB_APIKEY}"
        )
        enclosure = ET.SubElement(item, "enclosure")
        enclosure.set("url", dl_url)
        enclosure.set("length", str(item_data["size"]))
        enclosure.set("type", "application/x-bittorrent")

        # Torznab attributes — include both standard Newznab and custom category
        _add_attr(item, "category", "5000")
        _add_attr(item, "category", str(item_data["category_id"]))
        _add_attr(item, "size", str(item_data["size"]))
        _add_attr(item, "seeders", "1")
        _add_attr(item, "leechers", "0")
        _add_attr(item, "peers", "1")
        _add_attr(item, "downloadvolumefactor", "0")
        _add_attr(item, "uploadvolumefactor", "1")

    xml_decl = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body = ET.tostring(rss, encoding="unicode")
    return Response(content=xml_decl + body, media_type="application/xml")


def _add_attr(parent: ET.Element, name: str, value: str):
    attr = ET.SubElement(parent, f"{{{TORZNAB_NS}}}attr")
    attr.set("name", name)
    attr.set("value", value)
