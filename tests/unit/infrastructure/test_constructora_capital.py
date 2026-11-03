"""Unit tests for the Constructora Capital parser, on hand-written HTML (never scraped HTML)."""

import logging
from datetime import UTC, datetime

import pytest

from sobreplano.domain.catalog import GeoPoint, Municipality
from sobreplano.domain.errors import PageParseError
from sobreplano.domain.scraping import FetchedPage
from sobreplano.infrastructure.scraping.constructora_capital import (
    CAPITAL_ZONES,
    ConstructoraCapitalSite,
)

SITE = ConstructoraCapitalSite()
BASE = "https://www.constructoracapital.com"
AXIS = f"{BASE}/proyecto/1/medellin-y-alrededores/envigado/262/axis"
PLACE = (
    "https://www.google.com.co/maps/place/6.171977710068938+-75.59416941716492"
    "/@6.171977710068938,-75.59416941716492,17z"
)
WAZE_PLACE = (
    "https://www.waze.com/es/live-map/directions/co/antioquia/envigado/axis?to=place.ChIJ1Y"
)


def card(zone: str, project_id: int, slug: str) -> str:
    href = f"proyecto/1/medellin-y-alrededores/{zone}/{project_id}/{slug}"
    return f"""
    <li class="inventario_si"><a href="{href}">
      <div class="info"><p class="tipo">APARTAMENTOS</p>
      <h2 class="subrayado"><strong>{zone}</strong></h2><p class="precio">Desde $1</p></div>
    </a></li>"""


def listing(*cards: str) -> str:
    return f'<div class="content"><ul class="grid colx3 grid_proyectos">{"".join(cards)}</ul></div>'


def project_page(canonical: str | None = AXIS, map_link: str | None = PLACE) -> FetchedPage:
    head = f'<link rel="canonical" href="{canonical}"/>' if canonical else ""
    location = f'<li><a href="{map_link}">Llega con GoogleMaps</a></li>' if map_link else ""
    html = f"""<html><head>{head}</head><body>
      <div id="header"><a>74 Proyectos</a><a>Proyectos (41)</a></div>
      <div class="contactos_barra"><a href="{WAZE_PLACE}">Llega con Waze</a>{location}</div>
      <div id="p_landing"><p class="tipo">APARTAMENTOS</p><p>Desde $710,200,000</p></div>
      <div id="p_plantas">
        <p class="destacado torre">Planta Apartamento 60.01 m2 Área Total</p>
        <p class="precio">$ 710,200,000</p>
        <p class="destacado">ÁREA TOTAL: 60.01 m2</p><p>ÁREA PRIVADA: 54.06 m2</p>
      </div>
      <div id="p_avances_tit"><div>AXIS / AVANCES DE OBRA</div></div>
      <div id="p_avances"><p>ULTIMA PUBLICACIÓN</p><h4>Octubre 2026</h4></div>
      <div id="p_otrosproyectos_tit"><div>TAMBIÉN PUEDEN INTERESARTE / OTROS PROYECTOS</div></div>
      <div id="p_otrosproyectos"><ul><li><p>Sabaneta</p><p>Desde $558,700,000</p></li></ul></div>
      <div id="footer"><p>Oficina Medellín Calle 19 # 43G-85</p></div>
      <div id="postfooter"><p>Apartamentos en Rionegro</p></div>
    </body></html>"""
    return FetchedPage(
        url=AXIS, status=200, html=html, fetched_at=datetime(2026, 11, 2, tzinfo=UTC)
    )


def test_project_urls_keeps_cards_in_the_zone_table_as_absolute_urls() -> None:
    html = listing(
        card("envigado", 262, "axis"),
        card("camino-verde", 216, "verde-olivo"),
        card("envigado", 262, "axis"),  # listed twice
    )
    assert SITE.project_urls(html) == [
        AXIS,
        f"{BASE}/proyecto/1/medellin-y-alrededores/camino-verde/216/verde-olivo",
    ]


@pytest.mark.parametrize(
    ("zone", "slug"),
    [
        ("rionegro-los-colegios", "monte-rosa"),  # outside the Aburrá Valley
        ("santa-fe", "urbanity-office"),  # offices
        ("santa-fe", "urbanity-renta-selecta"),  # rental only
        ("tierra-firme", "turquesa"),  # sold out, discarded by name
    ],
)
def test_project_urls_skips_out_of_scope_cards(zone: str, slug: str) -> None:
    assert SITE.project_urls(listing(card(zone, 1, slug))) == []


def test_unknown_zone_is_skipped_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert SITE.project_urls(listing(card("barrio-nuevo", 300, "nuevo"))) == []
    assert "unknown Capital zone 'barrio-nuevo'" in caplog.text


def test_parse_project_reads_slug_municipality_and_location() -> None:
    parsed = SITE.parse_project(project_page())
    assert parsed is not None
    assert parsed.canonical_url == AXIS
    assert parsed.slug == "capital-axis"
    assert parsed.municipality is Municipality.ENVIGADO
    assert parsed.location == GeoPoint(lat=6.171977710068938, lon=-75.59416941716492)


def test_clean_text_keeps_the_floor_plans_and_drops_chrome_progress_and_other_projects() -> None:
    parsed = SITE.parse_project(project_page())
    assert parsed is not None
    assert "Planta Apartamento 60.01 m2 Área Total\n$ 710,200,000" in parsed.text
    assert "ÁREA PRIVADA: 54.06 m2" in parsed.text
    for noise in ("74 Proyectos", "Octubre 2026", "OTROS PROYECTOS", "558,700,000", "43G-85"):
        assert noise not in parsed.text


def test_page_without_coordinates_has_no_location() -> None:
    # Capital's Waze link names a place, not a point; with no Google link there is none.
    parsed = SITE.parse_project(project_page(map_link=None))
    assert parsed is not None
    assert parsed.location is None


@pytest.mark.parametrize(
    "canonical",
    [
        f"{BASE}/proyecto/1/medellin-y-alrededores/rionegro-los-colegios/242/monte-rosa",
        f"{BASE}/proyecto/1/medellin-y-alrededores/santa-fe/219/urbanity-office",
        f"{BASE}/proyecto/2/bogota-y-sabana/usaquen/100/otro",
        "https://example.com/proyecto/1/medellin-y-alrededores/envigado/262/axis",
    ],
)
def test_parse_project_returns_none_out_of_scope(canonical: str) -> None:
    assert SITE.parse_project(project_page(canonical=canonical)) is None


def test_missing_canonical_is_a_parse_error() -> None:
    with pytest.raises(PageParseError, match="canonical"):
        SITE.parse_project(project_page(canonical=None))


def test_coordinates_outside_the_valley_are_a_parse_error() -> None:
    swapped = "https://www.google.com.co/maps/place/-75.5941694+6.1719777/@x"
    with pytest.raises(PageParseError, match="swapped"):
        SITE.parse_project(project_page(map_link=swapped))


def test_zone_table_only_maps_to_aburra_valley_municipalities() -> None:
    assert set(CAPITAL_ZONES.values()) <= set(Municipality)
    assert not any(zone.startswith("rionegro") for zone in CAPITAL_ZONES)
