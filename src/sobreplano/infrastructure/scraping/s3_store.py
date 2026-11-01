"""Raw HTML in a private S3 bucket, with the same keys as the disk store."""

from typing import Protocol

from sobreplano.domain.scraping import FetchedPage, raw_page_key


class S3PutClient(Protocol):
    """The one boto3 S3 client method this store needs, so tests can pass a fake."""

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> object: ...


class S3RawPageStore:
    """RawPageStore that writes s3://{bucket}/{developer}/{YYYY-MM-DD}/{sha256}.html."""

    def __init__(self, bucket: str, client: S3PutClient) -> None:
        self._bucket = bucket
        self._client = client

    def save(self, developer_slug: str, page: FetchedPage) -> str:
        """Upload the page's HTML and return its key, relative to the bucket.

        Saving the same HTML twice the same day rewrites the same object with the
        same bytes, so it stays one object. Raises botocore.exceptions.ClientError
        (or BotoCoreError) if the upload fails.
        """
        key = raw_page_key(developer_slug, page)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=page.html.encode("utf-8"),
            ContentType="text/html; charset=utf-8",
        )
        return key
