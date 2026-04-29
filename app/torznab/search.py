import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from urllib.parse import quote

from fastapi.responses import Response

from app.channels import get_all_channels, get_channel_by_category, get_category_by_chat
from app.config import settings
from app.media import extract_media_info
from app.telegram_client import get_client

logger = logging.getLogger(__name__)

TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
NEWZNAB_NS = "http://www.newznab.com/DTD/2010/feeds/attributes/"

# Words too generic to be useful as standalone search terms — they'd match
# almost any message and produce flood waits with no signal.
_STOPWORDS = {
    "the", "a", "an", "of", "is", "in", "to", "and", "or", "for", "on",
    "el", "la", "los", "las", "de", "y", "o", "un", "una", "en",
}


def build_progressive_queries(raw_query: str) -> list[str]:
    """Build the list of queries to try per channel.

    A multi-word query is already specific enough — issuing shorter prefixes
    would just multiply the per-channel Telegram call volume across all
    channels and add noise to the results. We only fall back to a shorter
    variant for short queries (1-2 words), which are typical for series-name
    searches where the channel's filename may not match the full phrase.
    """
    words = raw_query.split()
    if not words or len(words) >= 3:
        return [raw_query]
    queries = [raw_query]
    if len(words) == 2 and words[0].lower() not in _STOPWORDS:
        queries.append(words[0])
    return queries


async def _resolve_paired_message(client, chat_id_int: int, message):
    """Return the message that carries downloadable media for this match.

    If `message` itself has media, returns it. Otherwise looks at the next
    message (id+1) — some channels post a title/description as plain text
    immediately followed by the file. Returns None if nothing usable.
    """
    if extract_media_info(message):
        return message
    try:
        next_msg = await client.get_messages(chat_id_int, message.id + 1)
    except Exception as e:
        logger.debug("Could not fetch next message %d: %s", message.id + 1, e)
        return None
    if not next_msg or getattr(next_msg, "empty", False):
        return None
    if extract_media_info(next_msg):
        return next_msg
    return None


def _build_link(username: str | None, chat_id_int: int, message_id: int) -> str:
    """Build a t.me link without needing a Chat object (avoids GetFullChannel)."""
    if username:
        return f"https://t.me/{username}/{message_id}"
    # t.me/c/ expects the channel ID stripped of the -100 prefix
    bare_id = str(chat_id_int).removeprefix("-100")
    return f"https://t.me/c/{bare_id}/{message_id}"


def _dedupe_by_guid(results: list[list[dict]]) -> list[dict]:
    """Flatten per-channel results, dropping items that share a guid.

    Defends against the same chat_id appearing under multiple categories
    in channels.json (would otherwise emit duplicate keys to the frontend).
    """
    seen: set[str] = set()
    items: list[dict] = []
    for sublist in results:
        for item in sublist:
            if item["guid"] in seen:
                continue
            seen.add(item["guid"])
            items.append(item)
    return items


async def _search_channel(chat_id: str, query: str, limit: int) -> list[dict]:
    """Search a single channel, returning items with media."""
    client = get_client()
    items = []
    seen_msg_ids: set[int] = set()
    try:
        chat_id_int = int(chat_id)
        # Read channel metadata from local mapping — calling client.get_chat()
        # triggers channels.GetFullChannel which flood-waits aggressively when
        # many channels are searched in parallel.
        ch_mapping = get_category_by_chat(chat_id)
        username = ch_mapping.get("username") if ch_mapping else None
        cat_id = ch_mapping["category_id"] if ch_mapping else 0
        async for message in client.search_messages(chat_id_int, query=query, limit=limit):
            paired = await _resolve_paired_message(client, chat_id_int, message)
            if paired is None or paired.id in seen_msg_ids:
                continue
            seen_msg_ids.add(paired.id)
            media_info = extract_media_info(paired)

            text_source = message.text or message.caption or ""
            title = media_info["filename"] or text_source[:200] or "Unknown"

            items.append({
                "title": title,
                "guid": f"{chat_id}:{paired.id}",
                "link": _build_link(username, chat_id_int, paired.id),
                "chat_id": chat_id,
                "msg_id": paired.id,
                "pub_date": paired.date or message.date,
                "size": media_info["size"],
                "category_id": cat_id,
                "description": text_source[:500],
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


_search_semaphore = asyncio.Semaphore(2)


async def _search_channel_throttled(chat_id: str, queries: list[str], limit: int) -> list[dict]:
    """Search with concurrency limit, trying progressively shorter queries."""
    async with _search_semaphore:
        for q in queries:
            logger.info("Searching channel %s with query: %r", chat_id, q)
            results = await _search_channel(chat_id, q, limit)
            if results:
                logger.info("Channel %s: %d results for %r", chat_id, len(results), q)
                return results
        logger.info("Channel %s: no results for any query", chat_id)
        return []


async def search_channels(
    channels: list[dict],
    query: str,
    limit: int,
    season: str | None = None,
    ep: str | None = None,
) -> list[dict]:
    """Run the full search pipeline across channels, returning sorted items.

    Shared between the Torznab XML endpoint and the v2 JSON endpoint so they
    can't drift apart.
    """
    if not channels:
        return []

    # Sonarr's t=tvsearch capability check sends an empty query; without it
    # we'd hit every channel for nothing. Cap the fan-out in that case.
    if not query:
        channels = channels[:5]

    per_channel = max(limit // len(channels), 10)
    queries = build_progressive_queries(query)
    tasks = [
        _search_channel_throttled(ch["chat_id"], queries, per_channel)
        for ch in channels
    ]
    results = await asyncio.gather(*tasks)

    items = _dedupe_by_guid(results)
    if season or ep:
        items = _filter_by_season_ep(items, season, ep)
    items.sort(key=lambda x: x["pub_date"], reverse=True)
    return items


def resolve_channels(cat: str | None) -> list[dict] | None:
    """Resolve the target channel list for a search.

    Returns None when `cat` is malformed (caller should surface an error).
    Falls back to all channels when `cat` is unset or doesn't map to any
    configured channel (so Sonarr/Radarr's standard 5000+ categories still
    return useful results).
    """
    if not cat:
        return get_all_channels()
    try:
        cat_ids = [int(c.strip()) for c in cat.split(",") if c.strip()]
    except ValueError:
        return None
    matched = [
        ch for cid in cat_ids
        if (ch := get_channel_by_category(cid)) is not None
    ]
    return matched or get_all_channels()


async def do_search(
    query: str | None,
    cat: str | None,
    offset: int,
    limit: int,
    season: str | None = None,
    ep: str | None = None,
) -> Response:
    """Execute search across channels and return Torznab RSS XML."""
    channels = resolve_channels(cat)
    if channels is None:
        from app.torznab.errors import torznab_error
        return torznab_error(201, "Invalid category ID")

    logger.info("Search: cat=%s → %d channel(s) resolved", cat, len(channels))
    raw_query = query or ""
    all_items = await search_channels(channels, raw_query, limit, season, ep)
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
