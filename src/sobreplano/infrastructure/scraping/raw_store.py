"""Chooses where raw HTML goes from Settings.raw_store: local disk or S3."""

from pathlib import Path

import boto3

from sobreplano.domain.ports import RawPageStore
from sobreplano.infrastructure.scraping.file_store import FileRawPageStore
from sobreplano.infrastructure.scraping.s3_store import S3PutClient, S3RawPageStore

S3_SCHEME = "s3://"


def build_raw_page_store(raw_store: str) -> RawPageStore:
    """Return an S3 store for "s3://bucket-name", otherwise a disk store rooted at raw_store.

    Raises:
        ValueError: if an s3:// value has no bucket name or has a path after it.
    """
    if not raw_store.startswith(S3_SCHEME):
        return FileRawPageStore(Path(raw_store))
    bucket = raw_store.removeprefix(S3_SCHEME)
    if not bucket or "/" in bucket:
        raise ValueError(f"RAW_STORE must be s3://bucket-name, got {raw_store!r}")
    # boto3-stubs only installs the s3 and ssm services, so the other overloads of
    # boto3.client are Unknown; the "s3" overload itself is fully typed.
    client: S3PutClient = boto3.client("s3")  # pyright: ignore[reportUnknownMemberType]
    return S3RawPageStore(bucket, client)
