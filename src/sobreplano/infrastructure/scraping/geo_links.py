"""Project coordinates from map links in a page, with a hand-kept table as the last resort."""

import re
from collections.abc import Mapping

from bs4 import BeautifulSoup

from sobreplano.domain.catalog import GeoPoint
from sobreplano.infrastructure.scraping.manual_locations import MANUAL_LOCATIONS

_NUMBER = r"(-?\d+(?:\.\d+)?)"
_SEPARATOR = r"(?:,|\+|%2C)"
# Latitude first in every pattern:
#   google.com/maps/dir//6.3296009,-75.5595542/@...        (Londoño Gómez)
#   google.com.co/maps/place/6.1719777+-75.5941694/@...     (Constructora Capital)
GOOGLE = re.compile(rf"google\.[a-z.]+/maps/(?:dir/|place)/{_NUMBER}{_SEPARATOR}{_NUMBER}")
#   waze.com/...?...to=ll.6.3296009%2C-75.5595542           (Londoño Gómez)
WAZE = re.compile(rf"waze\.com/\S*?[?&]to=ll\.{_NUMBER}{_SEPARATOR}{_NUMBER}")
# A bare "6.1719777,-75.5941694" inside a map URL (embeds, "@lat,lon"). Four decimals at
# least, so a price or an area never reads as a coordinate.
LOOSE = re.compile(r"(?<![\d.])(-?\d{1,2}\.\d{4,})\s*(?:,|%2C)\s*(-?\d{1,3}\.\d{4,})(?![\d.])")


def location_from_links(
    soup: BeautifulSoup,
    slug: str,
    manual: Mapping[str, GeoPoint] = MANUAL_LOCATIONS,
) -> GeoPoint | None:
    """The first point found in the page's map links, else the manual one, else None.

    Tries Google Maps links, then Waze links with coordinates, then a bare lat,lon inside
    any link or iframe URL that mentions "map", and only then manual[slug]. A link always
    wins, so once a developer publishes its map the manual entry stops being used. Waze
    links that carry only a place id (Constructora Capital) have no coordinates.

    Raises:
        DomainValidationError: if the coordinates found fall outside the Aburrá Valley.
    """
    urls = [
        value
        for tag in soup.select("a[href], iframe[src]")
        for value in (tag.get("href"), tag.get("src"))
        if isinstance(value, str)
    ]
    for pattern, candidates in (
        (GOOGLE, urls),
        (WAZE, urls),
        (LOOSE, [url for url in urls if "map" in url.casefold()]),
    ):
        for url in candidates:
            match = pattern.search(url)
            if match:
                return GeoPoint(lat=float(match.group(1)), lon=float(match.group(2)))
    return manual.get(slug)
