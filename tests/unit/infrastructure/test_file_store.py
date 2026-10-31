"""Unit tests for FileRawPageStore, writing into pytest's tmp_path."""

from datetime import UTC, datetime
from pathlib import Path

from sobreplano.domain.scraping import FetchedPage, content_sha256
from sobreplano.infrastructure.scraping.file_store import FileRawPageStore


def make_page(
    html: str = "<html>Primavela</html>",
    fetched_at: datetime = datetime(2026, 10, 30, 15, 0, tzinfo=UTC),
) -> FetchedPage:
    return FetchedPage(
        url="https://londonogomez.com/proyectos-vivienda/antioquia/bello/primavela",
        status=200,
        html=html,
        fetched_at=fetched_at,
    )


def test_saves_under_developer_day_and_hash(tmp_path: Path) -> None:
    page = make_page()
    key = FileRawPageStore(tmp_path).save("londono-gomez", page)
    assert key == f"londono-gomez/2026-10-30/{content_sha256(page.html)}.html"
    assert (tmp_path / key).read_text(encoding="utf-8") == page.html
    assert list(tmp_path.rglob("*.partial")) == []


def test_day_is_the_bogota_date(tmp_path: Path) -> None:
    # 03:00 UTC on the 31st is 22:00 on the 30th in Bogotá.
    page = make_page(fetched_at=datetime(2026, 10, 31, 3, 0, tzinfo=UTC))
    key = FileRawPageStore(tmp_path).save("londono-gomez", page)
    assert key.startswith("londono-gomez/2026-10-30/")


def test_same_html_twice_keeps_one_file(tmp_path: Path) -> None:
    store = FileRawPageStore(tmp_path)
    assert store.save("londono-gomez", make_page()) == store.save("londono-gomez", make_page())
    assert len(list(tmp_path.rglob("*.html"))) == 1


def test_non_ascii_html_round_trips(tmp_path: Path) -> None:
    page = make_page("<p>Área total: 55.58 m² · Itagüí</p>")
    key = FileRawPageStore(tmp_path).save("londono-gomez", page)
    assert (tmp_path / key).read_text(encoding="utf-8") == page.html


def test_content_sha256_is_hex_of_utf8_bytes() -> None:
    digest = content_sha256("Área")
    assert len(digest) == 64
    assert digest != content_sha256("Area")
