"""Deterministic parser for Constructora Capital: listing, zone table, map link, clean text."""

import logging
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from sobreplano.domain.catalog import GeoPoint, Municipality
from sobreplano.domain.errors import DomainValidationError, PageParseError
from sobreplano.domain.scraping import FetchedPage, ParsedProjectPage
from sobreplano.infrastructure.scraping.geo_links import location_from_links
from sobreplano.infrastructure.scraping.page_text import clean_text

logger = logging.getLogger(__name__)

BASE_URL = "https://www.constructoracapital.com"
HOSTS = {"constructoracapital.com", "www.constructoracapital.com"}
# /proyecto/1/medellin-y-alrededores/{zone}/{id}/{slug}; cards link to it relatively.
PROJECT_PATH = re.compile(
    r"^/?proyecto/1/medellin-y-alrededores/([a-z0-9-]+)/(\d+)/([a-z0-9-]+)/?$"
)
# Project slugs are unique across developers and Capital's are short ("axis", "lino").
SLUG_PREFIX = "capital-"

# The URL zone is sometimes a neighborhood, so the municipality comes from this table,
# never from the model. Checked on 2026-11-02 (docs/scrapers/constructora-capital.md);
# camino-verde from the Verde Olivo page's map, Waze path and sales room address.
CAPITAL_ZONES: dict[str, Municipality] = {
    "envigado": Municipality.ENVIGADO,
    "loma-del-escobero": Municipality.ENVIGADO,
    "camino-verde": Municipality.ENVIGADO,
    "itagui": Municipality.ITAGUI,
    "bello": Municipality.BELLO,
    "santa-ana": Municipality.BELLO,
    "bello-santa-ana": Municipality.BELLO,
    "niquia": Municipality.BELLO,
    "sabaneta": Municipality.SABANETA,
    "la-estrella": Municipality.LA_ESTRELLA,
    "ciudad-del-rio": Municipality.MEDELLIN,
    "guayabal-las-villas": Municipality.MEDELLIN,
    "san-antonio-de-prado": Municipality.MEDELLIN,
    "robledo-pajarito": Municipality.MEDELLIN,
}
SKIPPED_ZONE_PREFIXES = ("rionegro",)  # outside the Aburrá Valley
SKIPPED_SLUG_WORDS = ("office", "renta")  # offices and rental-only buildings (Urbanity)
# Projects left out by name, so their zone needs no entry and new projects there still warn.
SKIPPED_SLUGS = {
    "turquesa",  # Tierra Firme, sold out: discarded by the owner on 2026-11-02
}

# Removed before the clean text. The site has no <header>, <nav> or <footer> tags, so the
# chrome goes by id. Construction progress changes monthly and the other projects' cards
# change on every request: either would make the clean-text hash never repeat, and the
# cards also carry other projects' prices.
NOISE_SELECTORS = [
    "#header",
    "#footer",
    "#postfooter",
    ".contactos_barra",
    "#p_avances_tit",
    "#p_avances",
    "#p_otrosproyectos_tit",
    "#p_otrosproyectos",
]
# The dollar reference next to each price follows the exchange rate, so it changes on every
# business day and would make the clean-text hash never repeat. The same class also holds
# "Consultar precios y disponibilidad…", which stays: it tells the model there is no price.
USD_REFERENCE = re.compile(r"^\([\d.,]+ US\)\*?$")


class ConstructoraCapitalSite:
    """DeveloperSite for constructoracapital.com, Medellín listing (checked on 2026-11-02)."""

    slug = "constructora-capital"
    name = "Constructora Capital"
    website_url = BASE_URL
    listing_url = f"{BASE_URL}/proyectos/1/medellin-y-alrededores"

    def project_urls(self, listing_html: str) -> list[str]:
        """Absolute project URLs of the listing cards in the zone table.

        Skips Rionegro zones, projects skipped by name, offices and rental-only slugs.
        Any other zone not in CAPITAL_ZONES is skipped with a warning, so it can be added.
        """
        soup = BeautifulSoup(listing_html, "html.parser")
        urls: list[str] = []
        for link in soup.select("ul.grid_proyectos > li a[href]"):
            href = link.get("href")
            if not isinstance(href, str):
                continue
            match = PROJECT_PATH.match(href)
            if match is None or not _in_scope(match.group(1), match.group(3)):
                continue
            url = urljoin(f"{BASE_URL}/", href)
            if url not in urls:
                urls.append(url)
        return urls

    def parse_project(self, page: FetchedPage) -> ParsedProjectPage | None:
        """Canonical URL, municipality, slug, location and clean text of a project page.

        Returns None when the canonical URL is not a Medellín-listing project page in the
        zone table, or is an office or rental-only project. The slug gets SLUG_PREFIX;
        the project name the user sees comes from the extraction, not from the slug.

        Raises:
            PageParseError: if the canonical link is missing, or the page's coordinates
                fall outside the Aburrá Valley. A page with no map link is not an error:
                its location is None.
        """
        soup = BeautifulSoup(page.html, "html.parser")
        canonical = soup.select_one('link[rel="canonical"]')
        canonical_url = canonical.get("href") if canonical else None
        if not isinstance(canonical_url, str):
            raise PageParseError(f"no canonical link in {page.url}")

        parsed = urlparse(canonical_url)
        match = PROJECT_PATH.match(parsed.path)
        if parsed.hostname not in HOSTS or match is None:
            return None
        zone, page_slug = match.group(1), match.group(3)
        if not _in_scope(zone, page_slug):
            return None
        slug = f"{SLUG_PREFIX}{page_slug}"

        # Location before the clean text, which removes the links from the soup.
        location = _location(soup, slug, canonical_url)
        for noise in soup.select(", ".join(NOISE_SELECTORS)):
            noise.decompose()
        for usd in soup.select(".enDolares"):
            if USD_REFERENCE.match(usd.get_text(strip=True)):
                usd.decompose()
        return ParsedProjectPage(
            canonical_url=canonical_url,
            municipality=CAPITAL_ZONES[zone],
            slug=slug,
            location=location,
            text=clean_text(soup),
        )


def _in_scope(zone: str, slug: str) -> bool:
    if zone.startswith(SKIPPED_ZONE_PREFIXES) or slug in SKIPPED_SLUGS:
        return False
    if any(word in slug for word in SKIPPED_SLUG_WORDS):
        return False
    if zone not in CAPITAL_ZONES:
        logger.warning("unknown Capital zone %r (%s): skipped, add it to CAPITAL_ZONES", zone, slug)
        return False
    return True


def _location(soup: BeautifulSoup, slug: str, canonical_url: str) -> GeoPoint | None:
    try:
        return location_from_links(soup, slug)
    except DomainValidationError as error:
        raise PageParseError(f"{canonical_url}: {error}") from error
