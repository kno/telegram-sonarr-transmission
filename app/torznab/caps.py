import xml.etree.ElementTree as ET

from fastapi.responses import Response

from app.channels import get_all_channels
from app.config import settings


def build_caps_response() -> Response:
    root = ET.Element("caps")

    ET.SubElement(root, "server", version="1.0", title="Telegram Torznab")
    ET.SubElement(
        root, "limits",
        max=str(settings.MAX_LIMIT),
        default=str(settings.DEFAULT_LIMIT),
    )

    ET.SubElement(root, "registration", available="no", open="no")

    searching = ET.SubElement(root, "searching")
    ET.SubElement(searching, "search", available="yes", supportedParams="q")
    ET.SubElement(searching, "tv-search", available="yes", supportedParams="q,season,ep")
    ET.SubElement(searching, "movie-search", available="yes", supportedParams="q")

    categories = ET.SubElement(root, "categories")

    # Standard Newznab parent categories so Sonarr/Radarr recognize this indexer
    tv_cat = ET.SubElement(categories, "category", id="5000", name="TV")
    ET.SubElement(tv_cat, "subcat", id="5030", name="TV/SD")
    ET.SubElement(tv_cat, "subcat", id="5040", name="TV/HD")
    ET.SubElement(tv_cat, "subcat", id="5045", name="TV/UHD")
    movie_cat = ET.SubElement(categories, "category", id="2000", name="Movies")
    ET.SubElement(movie_cat, "subcat", id="2030", name="Movies/SD")
    ET.SubElement(movie_cat, "subcat", id="2040", name="Movies/HD")
    ET.SubElement(movie_cat, "subcat", id="2045", name="Movies/UHD")

    # Telegram channels as custom categories
    for ch in get_all_channels():
        ET.SubElement(
            categories, "category",
            id=str(ch["category_id"]),
            name=ch["name"],
        )

    xml_decl = '<?xml version="1.0" encoding="UTF-8"?>\n'
    body = ET.tostring(root, encoding="unicode")
    return Response(content=xml_decl + body, media_type="application/xml")
