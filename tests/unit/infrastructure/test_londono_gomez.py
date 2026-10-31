"""Unit tests for the Londoño Gómez parser, on hand-written HTML (never scraped HTML)."""

from datetime import UTC, datetime

import pytest

from sobreplano.domain.catalog import GeoPoint, Municipality
from sobreplano.domain.errors import PageParseError
from sobreplano.domain.scraping import FetchedPage
from sobreplano.infrastructure.scraping.londono_gomez import (
    LondonoGomezSite,
    municipality_from_name,
)

SITE = LondonoGomezSite()
MAP_LINK = "https://www.google.com/maps/dir//6.3296009,-75.5595542/@6.3296009,-75.5595542,16z"
CANONICAL = "https://londonogomez.com/proyectos-vivienda/antioquia/bello/primavela"


def card(node: int, title: str, project_type: str, municipality: str) -> str:
    return f"""
    <div class="views-row">
      <div class="views-field views-field-title"><span>{title}</span></div>
      <div class="views-field views-field-field-tipo-de-proyecto"><span>{project_type}</span></div>
      <div class="views-field views-field-nothing"><span>{municipality}</span></div>
      <div class="views-field views-field-nothing-3">
        <a href="/node/{node}">Más información del proyecto</a>
      </div>
    </div>"""


def listing(*cards: str) -> str:
    rows = "".join(cards)
    return f'<div class="view view-busqueda-proyectos"><div class="view-content">{rows}</div></div>'


def project_page(canonical: str | None = CANONICAL, map_link: str | None = MAP_LINK) -> FetchedPage:
    head = f'<link rel="canonical" href="{canonical}" />' if canonical else ""
    location = f'<a href="{map_link}">¿Como llegar con Google Maps?</a>' if map_link else ""
    html = f"""<html><head>{head}<style>.x{{color:red}}</style></head><body>
      <header><nav><a href="/">Inicio</a></nav></header>
      <form><label>Nombre completo</label><input name="name"></form>
      <h1>Primavela</h1>
      <div class="col-12 col-lg-4 detail-apartment">
        <h4>TIPO B</h4>
        <p>Desde <span class="price-apartament-types">$506.100.000 *</span></p>
        <p><strong>Área total: <span>55.58 m<sup>2</sup></span> *</strong></p>
      </div>
      {location}
      <script>var tracking = 1;</script>
      <footer>Política de privacidad</footer>
    </body></html>"""
    return FetchedPage(
        url="https://londonogomez.com/node/176344",
        status=200,
        html=html,
        fetched_at=datetime(2026, 10, 30, 15, 0, tzinfo=UTC),
    )


def test_project_urls_keeps_housing_cards_in_the_valley_as_absolute_urls() -> None:
    html = listing(
        card(176344, "Primavela", "Vivienda", "Bello"),
        card(70928, "Réflex Living", "Vivienda", "Sabaneta"),
        card(70876, "Costa Azul", "Vivienda", "La Estrella"),
    )
    assert SITE.project_urls(html) == [
        "https://londonogomez.com/node/176344",
        "https://londonogomez.com/node/70928",
        "https://londonogomez.com/node/70876",
    ]


@pytest.mark.parametrize(
    ("title", "project_type", "municipality"),
    [
        ("Atlántica Outlet", "Vivienda", "Bello"),
        ("Mint Natura outlet", "Vivienda", "Sabaneta"),
        ("prueba", "Vivienda", "Medellín"),
        ("Canto Lotes", "Lotes", "Medellín"),
        ("Vivaltta", "Oficinas", "Envigado"),
        ("HOTEL VIVALTTA", "Hotel", "Envigado"),
        ("Verde M", "", ""),
        ("Canto", "Vivienda", "Rionegro"),
        ("Viena", "Vivienda", "Bogotá"),
    ],
)
def test_project_urls_skips_out_of_scope_cards(
    title: str, project_type: str, municipality: str
) -> None:
    assert SITE.project_urls(listing(card(1, title, project_type, municipality))) == []


def test_project_urls_lists_each_node_once() -> None:
    html = listing(
        card(1, "Primavela", "Vivienda", "Bello"), card(1, "Primavela", "Vivienda", "Bello")
    )
    assert SITE.project_urls(html) == ["https://londonogomez.com/node/1"]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Medellín", Municipality.MEDELLIN),
        ("La Estrella", Municipality.LA_ESTRELLA),
        ("la-estrella", Municipality.LA_ESTRELLA),
        ("Itagüí", Municipality.ITAGUI),
        (" SABANETA ", Municipality.SABANETA),
        ("Rionegro", None),
        ("", None),
    ],
)
def test_municipality_from_name(name: str, expected: Municipality | None) -> None:
    assert municipality_from_name(name) == expected


def test_parse_project_reads_canonical_location_and_clean_text() -> None:
    parsed = SITE.parse_project(project_page())
    assert parsed is not None
    assert parsed.canonical_url == CANONICAL
    assert parsed.municipality is Municipality.BELLO
    assert parsed.slug == "primavela"
    # Latitude first, as in the map link: never swapped.
    assert parsed.location == GeoPoint(lat=6.3296009, lon=-75.5595542)
    assert "TIPO B\nDesde $506.100.000 *\nÁrea total: 55.58 m ² *" in parsed.text


@pytest.mark.parametrize("noise", ["Inicio", "Nombre completo", "tracking", "privacidad", "color"])
def test_clean_text_drops_chrome_scripts_and_forms(noise: str) -> None:
    parsed = SITE.parse_project(project_page())
    assert parsed is not None
    assert noise not in parsed.text


@pytest.mark.parametrize(
    "canonical",
    [
        "https://londonogomez.com/proyectos-vivienda/antioquia/bello/atlantica-outlet",
        "https://londonogomez.com/proyectos-vivienda/antioquia/rionegro/canto",
        "https://londonogomez.com/lotes/antioquia/rionegro/canto-lotes",
        "https://londonogomez.com/proyectos-vivienda/cundinamarca/bogota/viena",
        "https://example.com/proyectos-vivienda/antioquia/bello/primavela",
    ],
)
def test_parse_project_returns_none_out_of_scope(canonical: str) -> None:
    assert SITE.parse_project(project_page(canonical=canonical)) is None


def test_out_of_scope_page_needs_no_map_link() -> None:
    page = project_page(
        canonical="https://londonogomez.com/proyectos-vivienda/antioquia/rionegro/canto",
        map_link=None,
    )
    assert SITE.parse_project(page) is None


def test_missing_canonical_is_a_parse_error() -> None:
    with pytest.raises(PageParseError, match="canonical"):
        SITE.parse_project(project_page(canonical=None))


def test_missing_map_link_is_a_parse_error() -> None:
    with pytest.raises(PageParseError, match="Google Maps"):
        SITE.parse_project(project_page(map_link=None))


def test_swapped_coordinates_are_a_parse_error() -> None:
    swapped = "https://www.google.com/maps/dir//-75.5595542,6.3296009/@x"
    with pytest.raises(PageParseError, match="swapped"):
        SITE.parse_project(project_page(map_link=swapped))
