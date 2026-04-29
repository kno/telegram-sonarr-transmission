import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.media import extract_media_info
from app.torznab.search import (
    _build_link,
    _build_rss_response,
    _filter_by_season_ep,
    _search_channel,
    _search_channel_throttled,
    build_progressive_queries,
    do_search,
)


# ---------------------------------------------------------------------------
# Unit tests: pure helpers
# ---------------------------------------------------------------------------

class TestExtractMediaInfo:
    def test_with_document(self, mock_message):
        msg = mock_message(file_name="video.mkv", file_size=1000, mime_type="video/x-matroska")
        result = extract_media_info(msg)
        assert result["filename"] == "video.mkv"
        assert result["size"] == 1000
        assert result["mime_type"] == "video/x-matroska"

    def test_no_document(self, mock_message):
        msg = mock_message(has_document=False)
        assert extract_media_info(msg) is None

    def test_with_video(self, mock_message):
        msg = mock_message(file_name="ep.mp4", file_size=2000, mime_type="video/mp4", media_type="video")
        result = extract_media_info(msg)
        assert result["filename"] == "ep.mp4"
        assert result["size"] == 2000
        assert result["mime_type"] == "video/mp4"

    def test_missing_fields(self):
        msg = MagicMock()
        msg.document.file_name = None
        msg.document.file_size = None
        msg.document.mime_type = None
        result = extract_media_info(msg)
        assert result["filename"] is None
        assert result["size"] == 0
        assert result["mime_type"] == "application/octet-stream"


class TestBuildLink:
    def test_with_username(self):
        assert _build_link("mychan", -1001234, 5) == "https://t.me/mychan/5"

    def test_strips_minus_100_prefix(self):
        assert _build_link(None, -1002589145533, 251258) == "https://t.me/c/2589145533/251258"

    def test_no_username_no_prefix_to_strip(self):
        assert _build_link(None, 1234, 5) == "https://t.me/c/1234/5"


class TestFilterBySeasonEp:
    @pytest.mark.parametrize("title,season,ep,should_match", [
        ("Show.S02E03.720p.mkv", "2", "3", True),
        ("Show.s2e3.720p.mkv", "2", "3", True),
        ("Show.2x03.720p.mkv", "2", "3", True),
        ("Show.02x03.720p.mkv", "2", "3", True),
        ("Show.S02E03.720p.mkv", "1", "3", False),
        ("Show.S02E03.720p.mkv", "2", "4", False),
        ("Show.S02E03.720p.mkv", "2", None, True),
        ("Show.S03E01.720p.mkv", "2", None, False),
        ("random_file.mkv", "2", "3", False),
        ("Show.S10E05.720p.mkv", "10", "5", True),
        ("Show.2x03.720p.mkv", "2", None, True),
    ])
    def test_parametrized(self, title, season, ep, should_match):
        items = [{"title": title}]
        result = _filter_by_season_ep(items, season, ep)
        assert (len(result) == 1) == should_match

    def test_mixed_items(self):
        items = [
            {"title": "Show.S02E03.720p.mkv"},
            {"title": "Show.S02E04.720p.mkv"},
            {"title": "Other.S01E01.mkv"},
        ]
        result = _filter_by_season_ep(items, "2", "3")
        assert len(result) == 1
        assert result[0]["title"] == "Show.S02E03.720p.mkv"

    def test_no_season_no_ep_returns_empty(self):
        items = [{"title": "Show.S02E03.mkv"}]
        result = _filter_by_season_ep(items, None, None)
        assert result == []


class TestBuildRssResponse:
    def test_empty(self, test_settings):
        resp = _build_rss_response([], 0, 0)
        root = ET.fromstring(resp.body.decode())
        assert root.tag == "rss"
        channel = root.find("channel")
        assert channel is not None

    def test_with_items(self, test_settings):
        items = [{
            "title": "Test.S01E01.mkv",
            "guid": "-100:1",
            "link": "https://t.me/test/1",
            "chat_id": "-100",
            "msg_id": 1,
            "pub_date": datetime(2025, 1, 1, tzinfo=timezone.utc),
            "size": 1000,
            "category_id": 1000,
            "description": "test",
        }]
        resp = _build_rss_response(items, 1, 0)
        root = ET.fromstring(resp.body.decode())
        channel = root.find("channel")
        xml_items = channel.findall("item")
        assert len(xml_items) == 1
        assert xml_items[0].find("title").text == "Test.S01E01.mkv"
        enclosure = xml_items[0].find("enclosure")
        assert enclosure is not None
        assert enclosure.get("type") == "application/x-bittorrent"

    def test_pagination_offset(self, test_settings):
        resp = _build_rss_response([], 10, 5)
        root = ET.fromstring(resp.body.decode())
        ns = {"newznab": "http://www.newznab.com/DTD/2010/feeds/attributes/"}
        response_elem = root.find(".//newznab:response", ns)
        assert response_elem.get("offset") == "5"
        assert response_elem.get("total") == "10"


# ---------------------------------------------------------------------------
# Integration tests: search pipeline (mocked Telegram)
# ---------------------------------------------------------------------------

class TestSearchChannel:
    async def test_success(self, test_settings, mock_telegram_client, populated_channels, mock_message):
        msg = mock_message(msg_id=1, file_name="Show.S01E01.mkv", file_size=5000)

        async def fake_search(chat_id, query, limit):
            yield msg

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        items = await _search_channel("-1001234", "Show", 10)
        assert len(items) == 1
        assert items[0]["title"] == "Show.S01E01.mkv"

    async def test_no_results(self, test_settings, mock_telegram_client, populated_channels):
        async def empty_search(chat_id, query, limit):
            return
            yield

        mock_telegram_client.search_messages = MagicMock(side_effect=empty_search)
        items = await _search_channel("-1001234", "nothing", 10)
        assert items == []

    async def test_error_returns_empty(self, test_settings, mock_telegram_client, populated_channels):
        mock_telegram_client.search_messages = MagicMock(side_effect=Exception("Flood wait"))
        items = await _search_channel("-1001234", "test", 10)
        assert items == []

    async def test_text_match_pairs_with_next_video_message(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        """When the matching message is a plain text (title) and the next
        message carries the actual file, the result should point at the file
        message and inherit the title text."""
        text_msg = mock_message(
            msg_id=251257,
            has_document=False,
            text="The Last Spark of Hope",
        )
        video_msg = mock_message(
            msg_id=251258,
            file_name=None,
            file_size=12345,
            mime_type="video/mp4",
            media_type="video",
        )
        mock_telegram_client.get_messages = AsyncMock(return_value=video_msg)

        async def fake_search(chat_id, query, limit):
            yield text_msg

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        items = await _search_channel("-1001234", "spark of hope", 10)
        assert len(items) == 1
        item = items[0]
        # Title falls back to the matching text-message's text
        assert item["title"] == "The Last Spark of Hope"
        # Pointer is to the video message, not the text one
        assert item["msg_id"] == 251258
        assert item["guid"] == "-1001234:251258"
        assert item["size"] == 12345
        assert item["link"].endswith("/251258")

    async def test_text_match_dropped_when_next_message_has_no_media(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        """If the matching message is text and the next message also has no
        media, no item should be produced."""
        text_msg = mock_message(msg_id=10, has_document=False, text="just chatter")
        next_msg = mock_message(msg_id=11, has_document=False, text="more chatter")
        mock_telegram_client.get_messages = AsyncMock(return_value=next_msg)

        async def fake_search(chat_id, query, limit):
            yield text_msg

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        items = await _search_channel("-1001234", "anything", 10)
        assert items == []

    async def test_pairing_does_not_duplicate_when_media_match_already_seen(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        """If both a text-message (which would pair to id N+1) and message N+1
        itself match the search, dedupe by paired msg_id."""
        text_msg = mock_message(msg_id=100, has_document=False, text="Title For File")
        file_msg = mock_message(msg_id=101, file_name="file.mkv", file_size=999)
        mock_telegram_client.get_messages = AsyncMock(return_value=file_msg)

        async def fake_search(chat_id, query, limit):
            yield text_msg
            yield file_msg

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        items = await _search_channel("-1001234", "file", 10)
        assert len(items) == 1
        assert items[0]["msg_id"] == 101


class TestDoSearch:
    async def test_by_category(self, test_settings, mock_telegram_client, populated_channels, mock_message):
        msg = mock_message(msg_id=1, file_name="Result.mkv", file_size=1000)

        async def fake_search(chat_id, query, limit):
            yield msg

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        resp = await do_search("Result", "1000", 0, 50)
        root = ET.fromstring(resp.body.decode())
        items = root.findall(".//item")
        assert len(items) == 1

    async def test_empty_query_limits_channels(self, test_settings, mock_telegram_client, populated_channels, monkeypatch):
        # With 2 channels and no query, both should be searched (< 5 limit)
        search_calls = []

        async def fake_search(chat_id, query, limit):
            search_calls.append(chat_id)
            return
            yield

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        await do_search(None, None, 0, 50)
        assert len(search_calls) == 2  # Both channels searched (< 5 limit)

    async def test_with_season_episode_filter(self, test_settings, mock_telegram_client, populated_channels, mock_message):
        msgs = [
            mock_message(msg_id=1, file_name="Show.S02E03.mkv", file_size=1000),
            mock_message(msg_id=2, file_name="Show.S02E04.mkv", file_size=1000),
        ]

        async def fake_search(chat_id, query, limit):
            for m in msgs:
                yield m

        mock_telegram_client.search_messages = MagicMock(side_effect=fake_search)
        resp = await do_search("Show", "1000", 0, 50, season="2", ep="3")
        root = ET.fromstring(resp.body.decode())
        items = root.findall(".//item")
        assert len(items) == 1
        assert "S02E03" in items[0].find("title").text


# ---------------------------------------------------------------------------
# Query expansion: each search request must result in a bounded, predictable
# number of Telegram calls.
# ---------------------------------------------------------------------------

class TestBuildProgressiveQueries:
    def test_empty_query(self):
        assert build_progressive_queries("") == [""]

    def test_single_word(self):
        assert build_progressive_queries("Wednesday") == ["Wednesday"]

    def test_three_words_no_fallback(self):
        # Multi-word queries are specific enough — no shortened variants.
        assert build_progressive_queries("the office us") == ["the office us"]

    def test_five_words_no_fallback(self):
        # The user's pathological case.
        assert build_progressive_queries("the last spark of hope") == ["the last spark of hope"]

    def test_two_words_with_meaningful_first_word(self):
        # "Wednesday" alone is useful as a fallback for series searches.
        assert build_progressive_queries("Wednesday S02E03") == ["Wednesday S02E03", "Wednesday"]

    def test_two_words_with_stopword_first(self):
        # "the" alone would match everything → no fallback.
        assert build_progressive_queries("the office") == ["the office"]

    def test_two_words_spanish_stopword(self):
        assert build_progressive_queries("el chavo") == ["el chavo"]

    def test_whitespace_only_query(self):
        # Whitespace collapses to no words; we still issue the original query.
        assert build_progressive_queries("   ") == ["   "]


class _CallTracker:
    """Records every call to client.search_messages with (chat_id, query)."""
    def __init__(self, msgs_per_call: list = None, by_chat=None):
        self.calls: list[tuple[int, str]] = []
        self._msgs_per_call = msgs_per_call or []
        self._by_chat = by_chat or {}

    def make_search_messages(self):
        tracker = self

        def search_messages(chat_id, query, limit):
            tracker.calls.append((chat_id, query))

            async def gen():
                # Per-chat configured messages take precedence
                if tracker._by_chat and chat_id in tracker._by_chat:
                    for m in tracker._by_chat[chat_id]:
                        yield m
                    return
                if tracker._msgs_per_call:
                    for m in tracker._msgs_per_call:
                        yield m

            return gen()

        return MagicMock(side_effect=search_messages)


class TestSearchChannelThrottledCallCount:
    """`_search_channel_throttled` must call `_search_channel` once per query
    variant in order, stopping at the first one that returns results."""

    async def test_one_call_when_first_query_matches(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        msg = mock_message(msg_id=1, file_name="hit.mkv", file_size=10)
        tracker = _CallTracker(msgs_per_call=[msg])
        mock_telegram_client.search_messages = tracker.make_search_messages()

        result = await _search_channel_throttled("-1001234", ["full query", "shorter", "even shorter"], 10)

        assert len(result) == 1
        # Only the first variant should have been issued.
        assert tracker.calls == [(-1001234, "full query")]

    async def test_falls_back_when_first_query_empty(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        # First query: empty results. Second query: a hit.
        msg = mock_message(msg_id=1, file_name="hit.mkv", file_size=10)
        calls: list[tuple[int, str]] = []

        def search_messages(chat_id, query, limit):
            calls.append((chat_id, query))

            async def gen():
                if query == "second":
                    yield msg

            return gen()

        mock_telegram_client.search_messages = MagicMock(side_effect=search_messages)
        result = await _search_channel_throttled("-1001234", ["first", "second", "third"], 10)

        assert len(result) == 1
        # Stops at "second" — does NOT continue to "third".
        assert calls == [(-1001234, "first"), (-1001234, "second")]

    async def test_all_variants_tried_when_no_results(
        self, test_settings, mock_telegram_client, populated_channels
    ):
        calls: list[tuple[int, str]] = []

        def search_messages(chat_id, query, limit):
            calls.append((chat_id, query))

            async def gen():
                if False:
                    yield None  # never yields

            return gen()

        mock_telegram_client.search_messages = MagicMock(side_effect=search_messages)
        result = await _search_channel_throttled("-1001234", ["a", "b", "c"], 10)

        assert result == []
        assert calls == [(-1001234, "a"), (-1001234, "b"), (-1001234, "c")]


class TestDoSearchCallCount:
    """A single HTTP search request must touch each channel exactly once
    when the query is specific (3+ words). No GetFullChannel, no retries."""

    async def test_three_word_query_one_call_per_channel(
        self, test_settings, mock_telegram_client, populated_channels
    ):
        tracker = _CallTracker()
        mock_telegram_client.search_messages = tracker.make_search_messages()

        await do_search("the last spark of hope", None, 0, 50)

        # 2 channels in populated_channels, both queried once with the full query.
        assert len(tracker.calls) == 2
        chat_ids = sorted(c[0] for c in tracker.calls)
        assert chat_ids == [-1005678, -1001234]
        # All calls used the full query — no shortened variant.
        assert all(query == "the last spark of hope" for _, query in tracker.calls)

    async def test_one_word_query_one_call_per_channel(
        self, test_settings, mock_telegram_client, populated_channels
    ):
        tracker = _CallTracker()
        mock_telegram_client.search_messages = tracker.make_search_messages()

        await do_search("Lost", None, 0, 50)

        assert len(tracker.calls) == 2
        assert all(query == "Lost" for _, query in tracker.calls)

    async def test_two_word_query_falls_back_when_empty(
        self, test_settings, mock_telegram_client, populated_channels
    ):
        # Both channels return 0 for both variants → 2 channels × 2 variants = 4 calls.
        tracker = _CallTracker()
        mock_telegram_client.search_messages = tracker.make_search_messages()

        await do_search("Wednesday S02E03", None, 0, 50)

        assert len(tracker.calls) == 4
        queries = [q for _, q in tracker.calls]
        assert queries.count("Wednesday S02E03") == 2
        assert queries.count("Wednesday") == 2

    async def test_two_word_query_with_stopword_no_fallback(
        self, test_settings, mock_telegram_client, populated_channels
    ):
        # "the office": "the" is a stopword, so no fallback variant.
        tracker = _CallTracker()
        mock_telegram_client.search_messages = tracker.make_search_messages()

        await do_search("the office", None, 0, 50)

        assert len(tracker.calls) == 2
        assert all(query == "the office" for _, query in tracker.calls)

    async def test_get_chat_is_never_called(
        self, test_settings, mock_telegram_client, populated_channels
    ):
        # `client.get_chat` calls channels.GetFullChannel which flood-waits
        # aggressively when many channels are searched in parallel — the
        # search path must read channel metadata locally instead.
        tracker = _CallTracker()
        mock_telegram_client.search_messages = tracker.make_search_messages()
        mock_telegram_client.get_chat = AsyncMock(
            side_effect=AssertionError("get_chat must not be called from search path")
        )

        await do_search("the last spark of hope", None, 0, 50)

    async def test_no_call_when_channels_list_empty(
        self, test_settings, mock_telegram_client, monkeypatch
    ):
        import app.channels as ch_mod
        monkeypatch.setattr(ch_mod, "_channels", [])
        monkeypatch.setattr(ch_mod, "_by_category", {})
        monkeypatch.setattr(ch_mod, "_by_chat", {})

        tracker = _CallTracker()
        mock_telegram_client.search_messages = tracker.make_search_messages()

        await do_search("anything", None, 0, 50)

        assert tracker.calls == []


class TestPairedMediaCallCount:
    """When a text-only message matches, exactly one extra get_messages call
    is made for the (id+1) message — never more."""

    async def test_one_get_messages_per_text_match(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        text_msg = mock_message(msg_id=100, has_document=False, text="title")
        video_msg = mock_message(msg_id=101, file_name="file.mkv", file_size=99)

        tracker = _CallTracker(msgs_per_call=[text_msg])
        mock_telegram_client.search_messages = tracker.make_search_messages()
        mock_telegram_client.get_messages = AsyncMock(return_value=video_msg)

        items = await _search_channel("-1001234", "title", 10)

        assert len(items) == 1
        # Exactly one search call, and exactly one paired-message lookup.
        assert len(tracker.calls) == 1
        assert mock_telegram_client.get_messages.call_count == 1
        # Pairing reaches for id+1 of the matched message.
        args, kwargs = mock_telegram_client.get_messages.call_args
        assert args == (-1001234, 101)

    async def test_no_get_messages_when_message_already_has_media(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        msg = mock_message(msg_id=100, file_name="file.mkv", file_size=99)
        tracker = _CallTracker(msgs_per_call=[msg])
        mock_telegram_client.search_messages = tracker.make_search_messages()
        mock_telegram_client.get_messages = AsyncMock()

        await _search_channel("-1001234", "title", 10)

        # No need to look at the next message.
        assert mock_telegram_client.get_messages.call_count == 0


class TestEndToEndPairing:
    """Full search pipeline for the user's exact scenario: search hits a text
    message, the next message holds the actual file."""

    async def test_text_pairs_with_next_video_via_do_search(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        # Channel A: matches text msg 251257 paired with video msg 251258.
        # Channel B: no matches.
        text_msg = mock_message(
            msg_id=251257, has_document=False, text="The Last Spark of Hope"
        )
        video_msg = mock_message(
            msg_id=251258, file_name=None, file_size=42, mime_type="video/mp4",
            media_type="video",
        )

        def search_messages(chat_id, query, limit):
            async def gen():
                if chat_id == -1001234:
                    yield text_msg

            return gen()

        mock_telegram_client.search_messages = MagicMock(side_effect=search_messages)
        mock_telegram_client.get_messages = AsyncMock(return_value=video_msg)

        resp = await do_search("the last spark of hope", None, 0, 50)
        root = ET.fromstring(resp.body.decode())
        items = root.findall(".//item")
        assert len(items) == 1
        assert items[0].find("title").text == "The Last Spark of Hope"
        assert items[0].find("guid").text == "-1001234:251258"
        # search_messages called exactly once per channel (2 channels)
        assert mock_telegram_client.search_messages.call_count == 2
        # get_messages called exactly once (only for the one text match)
        assert mock_telegram_client.get_messages.call_count == 1

    async def test_concurrent_requests_each_count_independently(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        # Two parallel searches each issue their own per-channel calls.
        # Verify they don't bleed into each other (no skipped or shared calls).
        msg = mock_message(msg_id=1, file_name="x.mkv", file_size=10)

        def search_messages(chat_id, query, limit):
            async def gen():
                yield msg

            return gen()

        mock_telegram_client.search_messages = MagicMock(side_effect=search_messages)

        import asyncio as _asyncio
        await _asyncio.gather(
            do_search("query one", None, 0, 50),
            do_search("query two", None, 0, 50),
        )

        # 2 requests × 2 channels = 4 calls. No deduplication across requests.
        assert mock_telegram_client.search_messages.call_count == 4


class TestEdgeCasesAndErrorPaths:
    async def test_pairing_handles_get_messages_error(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        # If get_messages raises (flood, network, etc.), the text-only match
        # is silently dropped — the search must still complete.
        text_msg = mock_message(msg_id=100, has_document=False, text="title")
        tracker = _CallTracker(msgs_per_call=[text_msg])
        mock_telegram_client.search_messages = tracker.make_search_messages()
        mock_telegram_client.get_messages = AsyncMock(side_effect=Exception("flood"))

        items = await _search_channel("-1001234", "title", 10)
        assert items == []

    async def test_pairing_handles_empty_next_message(
        self, test_settings, mock_telegram_client, populated_channels, mock_message
    ):
        # Pyrogram returns an "empty" message marker when the slot is deleted.
        text_msg = mock_message(msg_id=100, has_document=False, text="title")
        empty_next = MagicMock()
        empty_next.empty = True
        empty_next.document = None
        empty_next.video = None

        tracker = _CallTracker(msgs_per_call=[text_msg])
        mock_telegram_client.search_messages = tracker.make_search_messages()
        mock_telegram_client.get_messages = AsyncMock(return_value=empty_next)

        items = await _search_channel("-1001234", "title", 10)
        assert items == []

    async def test_invalid_cat_parameter_returns_torznab_error(
        self, test_settings, mock_telegram_client, populated_channels
    ):
        resp = await do_search("anything", "not-a-number", 0, 50)
        body = resp.body.decode()
        assert "<error" in body
        assert resp.status_code == 200

    async def test_unknown_cat_falls_back_to_all_channels(
        self, test_settings, mock_telegram_client, populated_channels
    ):
        # Newznab category 5000 doesn't match any of our custom channels —
        # fall back to searching every channel.
        tracker = _CallTracker()
        mock_telegram_client.search_messages = tracker.make_search_messages()

        await do_search("the last spark of hope", "5000", 0, 50)

        # Both channels searched (fallback behavior).
        assert len(tracker.calls) == 2

    async def test_specific_cat_only_searches_matching_channel(
        self, test_settings, mock_telegram_client, populated_channels
    ):
        # Category 1000 maps to chat_id -1001234 only.
        tracker = _CallTracker()
        mock_telegram_client.search_messages = tracker.make_search_messages()

        await do_search("the last spark of hope", "1000", 0, 50)

        assert len(tracker.calls) == 1
        assert tracker.calls[0][0] == -1001234

    async def test_dedupes_guid_across_channels(
        self, test_settings, mock_telegram_client, monkeypatch, mock_message
    ):
        # Defense-in-depth: if channels.json ever has a duplicate chat_id
        # entry (different category_id), the same file would otherwise be
        # emitted twice with the same guid and crash the frontend's
        # keyed each-block. Verify dedupe holds.
        import app.channels as ch_mod
        dup_channels = [
            {"chat_id": "-1001234", "category_id": 1000, "name": "A", "username": "a"},
            {"chat_id": "-1001234", "category_id": 1001, "name": "A2", "username": "a"},
        ]
        monkeypatch.setattr(ch_mod, "_channels", dup_channels)
        monkeypatch.setattr(ch_mod, "_by_category", {c["category_id"]: c for c in dup_channels})
        monkeypatch.setattr(ch_mod, "_by_chat", {c["chat_id"]: c for c in dup_channels})

        msg = mock_message(msg_id=42, file_name="dup.mkv", file_size=10)
        tracker = _CallTracker(msgs_per_call=[msg])
        mock_telegram_client.search_messages = tracker.make_search_messages()

        resp = await do_search("anything specific here", None, 0, 50)
        root = ET.fromstring(resp.body.decode())
        items = root.findall(".//item")
        guids = [i.find("guid").text for i in items]
        assert len(guids) == len(set(guids))  # all unique
        assert guids.count("-1001234:42") == 1


class TestHttpEndpointCallCount:
    """Through the live FastAPI router — verify the HTTP layer doesn't
    introduce duplicate calls."""

    async def test_single_http_request_one_call_per_channel(
        self, async_client, mock_telegram_client, mock_message, test_settings
    ):
        tracker = _CallTracker()
        mock_telegram_client.search_messages = tracker.make_search_messages()

        resp = await async_client.get(
            "/api",
            params={
                "t": "search",
                "q": "the last spark of hope",
                "apikey": test_settings.TORZNAB_APIKEY,
            },
        )
        assert resp.status_code == 200
        # 2 channels in populated_channels → exactly 2 calls.
        assert len(tracker.calls) == 2
        assert all(q == "the last spark of hope" for _, q in tracker.calls)
