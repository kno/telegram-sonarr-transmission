import xml.etree.ElementTree as ET

import pytest

from app.torznab.errors import torznab_error, ERRORS


@pytest.mark.parametrize("code,expected_desc", [
    (100, "Incorrect user credentials"),
    (200, "Missing parameter"),
    (201, "Incorrect parameter"),
    (202, "No such function"),
    (300, "No items found"),
])
def test_torznab_error_default_descriptions(code, expected_desc):
    resp = torznab_error(code)
    root = ET.fromstring(resp.body.decode())
    assert root.get("code") == str(code)
    assert root.get("description") == expected_desc


def test_torznab_error_custom_description():
    resp = torznab_error(201, "Custom error text")
    root = ET.fromstring(resp.body.decode())
    assert root.get("code") == "201"
    assert root.get("description") == "Custom error text"


def test_torznab_error_unknown_code():
    resp = torznab_error(999)
    root = ET.fromstring(resp.body.decode())
    assert root.get("code") == "999"
    assert root.get("description") == "Unknown error"


def test_torznab_error_response_type():
    resp = torznab_error(100)
    assert resp.media_type == "application/xml"
    assert resp.status_code == 200


def test_torznab_error_valid_xml():
    resp = torznab_error(100)
    body = resp.body.decode()
    assert body.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    root = ET.fromstring(body)
    assert root.tag == "error"
