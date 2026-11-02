"""Raw HTML on local disk, under data/raw/ (git-ignored); the Lambda uses s3_store instead."""

from pathlib import Path

from sobreplano.domain.scraping import FetchedPage, raw_page_key

DEFAULT_ROOT = Path("data/raw")


class FileRawPageStore:
    """RawPageStore that writes {root}/{developer}/{YYYY-MM-DD}/{sha256}.html."""

    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self._root = root

    def save(self, developer_slug: str, page: FetchedPage) -> str:
        """Write the page's HTML and return its storage key, relative to the root.

        Saving the same HTML twice the same day is a no-op: the content decides the name.
        """
        key = raw_page_key(developer_slug, page)
        path = self._root / key
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write then rename, so an interrupted run never leaves a truncated file behind.
            partial = path.with_suffix(".html.partial")
            partial.write_text(page.html, encoding="utf-8")
            partial.replace(path)
        return key
