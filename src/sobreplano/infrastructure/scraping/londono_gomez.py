"""Deterministic parser for Londoño Gómez: listing cards, canonical URL, map link, clean text."""

import re
import unicodedata
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from sobreplano.domain.catalog import GeoPoint, Municipality
from sobreplano.domain.errors import DomainValidationError, PageParseError
from sobreplano.domain.scraping import FetchedPage, ParsedProjectPage
from sobreplano.infrastructure.scraping.geo_links import location_from_links
from sobreplano.infrastructure.scraping.page_text import clean_text

BASE_URL = "https://londonogomez.com"
HOSTS = {"londonogomez.com", "www.londonogomez.com"}
CANONICAL_PATH = re.compile(r"^/proyectos-vivienda/antioquia/([a-z0-9-]+)/([a-z0-9-]+)/?$")
SKIPPED_TITLE_WORDS = ("outlet", "prueba")
HOUSING_TYPE = "vivienda"


class LondonoGomezSite:
    """DeveloperSite for londonogomez.com (selectors checked on 2026-10-30)."""

    slug = "londono-gomez"
    name = "Londoño Gómez"
    website_url = BASE_URL
    listing_url = f"{BASE_URL}/proyectos-vivienda"

    def project_urls(self, listing_html: str) -> list[str]:
        """Absolute /node/N URLs of housing cards in Aburrá Valley municipalities.

        Skips a card whose title says "outlet" or "prueba", whose type is not housing
        (lots, offices, hotel or empty) or whose municipality is not a Municipality.
        """
        soup = BeautifulSoup(listing_html, "html.parser")
        urls: list[str] = []
        for card in soup.select(".view-busqueda-proyectos .views-row"):
            title = _field_text(card, ".views-field-title").casefold()
            if any(word in title for word in SKIPPED_TITLE_WORDS):
                continue
            if _field_text(card, ".views-field-field-tipo-de-proyecto").casefold() != HOUSING_TYPE:
                continue
            if municipality_from_name(_field_text(card, ".views-field-nothing")) is None:
                continue
            link = card.select_one('a[href^="/node/"]')
            href = link.get("href") if link else None
            if isinstance(href, str):
                url = urljoin(BASE_URL, href)
                if url not in urls:
                    urls.append(url)
        return urls

    def parse_project(self, page: FetchedPage) -> ParsedProjectPage | None:
        """Canonical URL, municipality, slug, location and clean text of a project page.

        Returns None when the canonical URL is not a housing page in a Municipality or its
        slug says "outlet": the page is out of scope and must not be stored or extracted.

        Raises:
            PageParseError: if the canonical link is missing, or the coordinates of an
                in-scope page fall outside the Aburrá Valley. A page with no map link and
                no manual location is not an error: its location is None.
        """
        soup = BeautifulSoup(page.html, "html.parser")
        canonical = soup.select_one('link[rel="canonical"]')
        canonical_url = canonical.get("href") if canonical else None
        if not isinstance(canonical_url, str):
            raise PageParseError(f"no canonical link in {page.url}")

        parsed = urlparse(canonical_url)
        match = CANONICAL_PATH.match(parsed.path)
        if parsed.hostname not in HOSTS or match is None:
            return None
        municipality = municipality_from_name(match.group(1))
        slug = match.group(2)
        if municipality is None or "outlet" in slug:
            return None

        return ParsedProjectPage(
            canonical_url=canonical_url,
            municipality=municipality,
            slug=slug,
            location=self._location(soup, slug, canonical_url),
            text=clean_text(soup),
        )

    def _location(self, soup: BeautifulSoup, slug: str, canonical_url: str) -> GeoPoint | None:
        # Must run before clean_text, which removes the links from the soup.
        try:
            return location_from_links(soup, slug)
        except DomainValidationError as error:
            raise PageParseError(f"{canonical_url}: {error}") from error


def municipality_from_name(name: str) -> Municipality | None:
    """Municipality from a card label ("La Estrella") or URL segment ("la-estrella")."""
    without_accents = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[\s-]+", "_", without_accents.strip().lower())
    try:
        return Municipality(key)
    except ValueError:
        return None


def _field_text(card: Tag, selector: str) -> str:
    field = card.select_one(selector)
    return field.get_text(" ", strip=True) if field else ""
