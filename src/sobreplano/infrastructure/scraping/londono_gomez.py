"""Deterministic parser for Londoño Gómez: listing cards, canonical URL, map link, clean text."""

import re
import unicodedata
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from sobreplano.domain.catalog import GeoPoint, Municipality
from sobreplano.domain.errors import DomainValidationError, PageParseError
from sobreplano.domain.scraping import FetchedPage, ParsedProjectPage

BASE_URL = "https://londonogomez.com"
HOSTS = {"londonogomez.com", "www.londonogomez.com"}
CANONICAL_PATH = re.compile(r"^/proyectos-vivienda/antioquia/([a-z0-9-]+)/([a-z0-9-]+)/?$")
# Directions link: https://www.google.com/maps/dir//6.3296009,-75.5595542/@..., lat then lon.
MAP_COORDINATES = re.compile(r"google\.[a-z.]+/maps/dir//(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")
SKIPPED_TITLE_WORDS = ("outlet", "prueba")
HOUSING_TYPE = "vivienda"
# Page chrome and the contact form: noise for the model, and the form is about personal data.
NOISE_TAGS = [
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "template",
    "header",
    "footer",
    "nav",
    "form",
]
BLOCK_END = "\x00"
BLOCK_TAGS = ["p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section"]


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
            PageParseError: if the canonical link is missing, or an in-scope page has no
                map link or its coordinates fall outside the Aburrá Valley.
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
            location=_location(soup, canonical_url),
            text=clean_text(soup),
        )


def municipality_from_name(name: str) -> Municipality | None:
    """Municipality from a card label ("La Estrella") or URL segment ("la-estrella")."""
    without_accents = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[\s-]+", "_", without_accents.strip().lower())
    try:
        return Municipality(key)
    except ValueError:
        return None


def clean_text(soup: BeautifulSoup) -> str:
    """Visible text without page chrome, one block per line. Mutates the soup."""
    for tag in soup(NOISE_TAGS):
        tag.decompose()
    # "55.58 m<sup>2</sup>" would otherwise read "55.58 m 2".
    for sup in soup("sup"):
        sup.replace_with("²" if sup.get_text(strip=True) == "2" else sup.get_text())
    # Line breaks only after blocks, so inline pieces ("Desde <span>$506.100.000</span>")
    # stay on one line. The source HTML's own newlines are just whitespace, hence the marker.
    for block in soup(BLOCK_TAGS):
        block.append(BLOCK_END)
    text = re.sub(r"\s+", " ", soup.get_text(" "))
    lines = (line.strip() for line in text.split(BLOCK_END))
    return "\n".join(line for line in lines if line)


def _field_text(card: Tag, selector: str) -> str:
    field = card.select_one(selector)
    return field.get_text(" ", strip=True) if field else ""


def _location(soup: BeautifulSoup, canonical_url: str) -> GeoPoint:
    for link in soup.select('a[href*="/maps/dir/"]'):
        href = link.get("href")
        match = MAP_COORDINATES.search(href) if isinstance(href, str) else None
        if match:
            try:
                return GeoPoint(lat=float(match.group(1)), lon=float(match.group(2)))
            except DomainValidationError as error:
                raise PageParseError(f"{canonical_url}: {error}") from error
    raise PageParseError(f"no Google Maps directions link in {canonical_url}")
