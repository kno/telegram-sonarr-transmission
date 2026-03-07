import xml.etree.ElementTree as ET

from fastapi.responses import Response

ERRORS = {
    100: "Incorrect user credentials",
    200: "Missing parameter",
    201: "Incorrect parameter",
    202: "No such function",
    300: "No items found",
}


def torznab_error(code: int, description: str | None = None) -> Response:
    desc = description or ERRORS.get(code, "Unknown error")
    root = ET.Element("error")
    root.set("code", str(code))
    root.set("description", desc)
    xml_decl = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body = ET.tostring(root, encoding="unicode")
    return Response(content=xml_decl + body, media_type="application/xml", status_code=200)
