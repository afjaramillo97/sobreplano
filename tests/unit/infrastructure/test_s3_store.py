"""Unit tests for S3RawPageStore and the raw store factory, with a fake S3 client."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sobreplano.domain.scraping import FetchedPage, content_sha256
from sobreplano.infrastructure.scraping.file_store import FileRawPageStore
from sobreplano.infrastructure.scraping.raw_store import build_raw_page_store
from sobreplano.infrastructure.scraping.s3_store import S3RawPageStore


@dataclass
class FakeS3:
    objects: dict[tuple[str, str], tuple[bytes, str]] = field(
        default_factory=dict[tuple[str, str], tuple[bytes, str]]
    )

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> object:
        self.objects[(Bucket, Key)] = (Body, ContentType)
        return {}


def make_page(
    html: str = "<p>Área total: 55.58 m² · Itagüí</p>",
    fetched_at: datetime = datetime(2026, 10, 31, 3, 0, tzinfo=UTC),
) -> FetchedPage:
    return FetchedPage(
        url="https://londonogomez.com/proyectos-vivienda/antioquia/bello/primavela",
        status=200,
        html=html,
        fetched_at=fetched_at,
    )


def test_uploads_utf8_html_under_the_bogota_day() -> None:
    s3 = FakeS3()
    page = make_page()
    key = S3RawPageStore("raw-bucket", s3).save("londono-gomez", page)
    # 03:00 UTC on the 31st is 22:00 on the 30th in Bogotá.
    assert key == f"londono-gomez/2026-10-30/{content_sha256(page.html)}.html"
    assert s3.objects[("raw-bucket", key)] == (
        page.html.encode("utf-8"),
        "text/html; charset=utf-8",
    )


def test_same_key_as_the_disk_store(tmp_path: Path) -> None:
    page = make_page()
    s3_key = S3RawPageStore("raw-bucket", FakeS3()).save("londono-gomez", page)
    assert s3_key == FileRawPageStore(tmp_path).save("londono-gomez", page)


def test_same_html_twice_keeps_one_object() -> None:
    s3 = FakeS3()
    store = S3RawPageStore("raw-bucket", s3)
    store.save("londono-gomez", make_page())
    store.save("londono-gomez", make_page())
    assert len(s3.objects) == 1


def test_factory_defaults_to_disk(tmp_path: Path) -> None:
    assert isinstance(build_raw_page_store(str(tmp_path)), FileRawPageStore)


def test_factory_builds_s3_for_an_s3_url(monkeypatch: pytest.MonkeyPatch) -> None:
    # boto3 needs a region to build a client; it opens no connection until a call.
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    assert isinstance(build_raw_page_store("s3://raw-bucket"), S3RawPageStore)


@pytest.mark.parametrize("value", ["s3://", "s3://raw-bucket/prefix"])
def test_factory_rejects_a_bad_s3_url(value: str) -> None:
    with pytest.raises(ValueError, match="s3://bucket-name"):
        build_raw_page_store(value)
