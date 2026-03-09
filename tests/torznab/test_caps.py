import xml.etree.ElementTree as ET

import pytest

from app.torznab.caps import build_caps_response


class TestCaps:
    def test_response_structure(self, test_settings, populated_channels):
        resp = build_caps_response()
        root = ET.fromstring(resp.body.decode())
        assert root.tag == "caps"
        tags = [child.tag for child in root]
        assert "server" in tags
        assert "limits" in tags
        assert "searching" in tags
        assert "categories" in tags

    def test_standard_categories(self, test_settings, populated_channels):
        resp = build_caps_response()
        root = ET.fromstring(resp.body.decode())
        categories = root.find("categories")
        cat_ids = [c.get("id") for c in categories.findall("category")]
        assert "5000" in cat_ids
        assert "2000" in cat_ids

    def test_channel_categories(self, test_settings, populated_channels):
        resp = build_caps_response()
        root = ET.fromstring(resp.body.decode())
        categories = root.find("categories")
        cat_ids = [c.get("id") for c in categories.findall("category")]
        assert "1000" in cat_ids
        assert "1001" in cat_ids

    def test_empty_channels(self, test_settings, monkeypatch):
        monkeypatch.setattr("app.torznab.caps.get_all_channels", lambda: [])
        resp = build_caps_response()
        root = ET.fromstring(resp.body.decode())
        categories = root.find("categories")
        cat_ids = [c.get("id") for c in categories.findall("category")]
        # Only standard categories
        assert "5000" in cat_ids
        assert "2000" in cat_ids
        assert len(categories.findall("category")) == 2

    def test_search_capabilities(self, test_settings, populated_channels):
        resp = build_caps_response()
        root = ET.fromstring(resp.body.decode())
        searching = root.find("searching")
        search = searching.find("search")
        assert search.get("available") == "yes"
        assert search.get("supportedParams") == "q"
        tv = searching.find("tv-search")
        assert tv.get("available") == "yes"
        assert "season" in tv.get("supportedParams")
        movie = searching.find("movie-search")
        assert movie.get("available") == "yes"

    def test_limits(self, test_settings, populated_channels):
        resp = build_caps_response()
        root = ET.fromstring(resp.body.decode())
        limits = root.find("limits")
        assert limits.get("max") == str(test_settings.MAX_LIMIT)
        assert limits.get("default") == str(test_settings.DEFAULT_LIMIT)
