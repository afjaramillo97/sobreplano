"""Raw HTML on local disk, under data/raw/ (git-ignored); SPEC 05 swaps it for S3."""

from pathlib import Path
from zoneinfo import ZoneInfo

from sobreplano.domain.scraping import FetchedPage, content_sha256

DEFAULT_ROOT = Path("data/raw")
BOGOTA = ZoneInfo("America/Bogota")


class FileRawPageStore:
    """RawPageStore that writes {root}/{developer}/{YYYY-MM-DD}/{sha256}.html.

    The day is the Bogotá date of fetched_at, the same day the price observation gets.
    """

    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self._root = root

    def save(self, developer_slug: str, page: FetchedPage) -> str:
        """Write the page's HTML and return its storage key, relative to the root.

        Saving the same HTML twice the same day is a no-op: the content decides the name.
        """
        day = page.fetched_at.astimezone(BOGOTA).date().isoformat()
        key = f"{developer_slug}/{day}/{content_sha256(page.html)}.html"
        path = self._root / key
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write then rename, so an interrupted run never leaves a truncated file behind.
            partial = path.with_suffix(".html.partial")
            partial.write_text(page.html, encoding="utf-8")
            partial.replace(path)
        return key
