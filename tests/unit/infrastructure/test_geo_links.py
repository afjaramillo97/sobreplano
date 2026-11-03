"""Unit tests for map-link coordinates and the manual locations table, on hand-written HTML."""

import pytest
from bs4 import BeautifulSoup

from sobreplano.domain.catalog import GeoPoint
from sobreplano.domain.errors import DomainValidationError
from sobreplano.infrastructure.scraping.geo_links import location_from_links
from sobreplano.infrastructure.scraping.manual_locations import MANUAL_LOCATIONS

PELDAR = GeoPoint(lat=6.171977710068938, lon=-75.59416941716492)
PRIMAVELA = GeoPoint(lat=6.3296009, lon=-75.5595542)
MANUAL = {"ezzenti": GeoPoint(lat=6.2731, lon=-75.5871)}


def soup(*tags: str) -> BeautifulSoup:
    return BeautifulSoup(f"<html><body>{''.join(tags)}</body></html>", "html.parser")


def link(href: str) -> str:
    return f'<a href="{href}">Cómo llegar</a>'


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        (
            link(
                "https://www.google.com/maps/dir//6.3296009,-75.5595542/@6.3296009,-75.5595542,16z"
            ),
            PRIMAVELA,
        ),
        (
            link(
                "https://www.google.com.co/maps/place/6.171977710068938+-75.59416941716492"
                "/@6.171977710068938,-75.59416941716492,17z"
            ),
            PELDAR,
        ),
        (
            link(
                "https://www.waze.com/es-419/live-map/directions?utm_source=x&to=ll.6.3296009%2C-75.5595542"
            ),
            PRIMAVELA,
        ),
        (
            '<iframe src="https://maps.google.com/maps?q=6.3296009,-75.5595542&output=embed"></iframe>',
            PRIMAVELA,
        ),
    ],
    ids=["google-dir", "google-place", "waze-ll", "loose-in-map-embed"],
)
def test_reads_each_kind_of_link(tag: str, expected: GeoPoint) -> None:
    assert location_from_links(soup(tag), "primavela", MANUAL) == expected


def test_google_wins_over_waze() -> None:
    waze = link("https://www.waze.com/live-map/directions?to=ll.6.3296009%2C-75.5595542")
    google = link("https://www.google.com.co/maps/place/6.171977710068938+-75.59416941716492/@x")
    assert location_from_links(soup(waze, google), "primavela", MANUAL) == PELDAR


def test_waze_place_id_has_no_coordinates() -> None:
    # Constructora Capital's Waze links name a Google place, not a point.
    waze = link(
        "https://www.waze.com/es/live-map/directions/co/antioquia/envigado/acento-ciudad-peldar"
        "?to=place.ChIJ1Y-YUACDRo4R_y8WWptUbfU"
    )
    assert location_from_links(soup(waze), "primavela", MANUAL) is None


def test_loose_numbers_outside_map_urls_are_ignored() -> None:
    other = link("https://example.com/precio?valor=6.3296009,-75.5595542")
    assert (
        location_from_links(soup(other, "<p>6.3296009,-75.5595542</p>"), "primavela", MANUAL)
        is None
    )


def test_no_links_gives_none() -> None:
    assert location_from_links(soup("<p>Ezzenti Apartamentos</p>"), "primavela", MANUAL) is None


def test_coordinates_outside_the_valley_raise() -> None:
    swapped = link("https://www.google.com/maps/dir//-75.5595542,6.3296009/@x")
    with pytest.raises(DomainValidationError, match="swapped"):
        location_from_links(soup(swapped), "primavela", MANUAL)


def test_manual_location_is_the_last_resort() -> None:
    assert location_from_links(soup("<p>Sin mapa</p>"), "ezzenti", MANUAL) == MANUAL["ezzenti"]


def test_a_published_map_link_wins_over_the_manual_location() -> None:
    google = link("https://www.google.com/maps/dir//6.3296009,-75.5595542/@x")
    assert location_from_links(soup(google), "ezzenti", MANUAL) == PRIMAVELA


@pytest.mark.parametrize("slug", sorted(MANUAL_LOCATIONS))
def test_every_manual_location_is_a_valid_point(slug: str) -> None:
    # GeoPoint already checks the range when the module is imported; this re-checks it
    # so a bad entry shows up as a failing test with the slug in its name.
    point = MANUAL_LOCATIONS[slug]
    assert GeoPoint(lat=point.lat, lon=point.lon) == point
