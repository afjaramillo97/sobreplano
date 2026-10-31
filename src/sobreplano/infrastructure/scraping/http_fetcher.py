"""Polite HTTP fetcher: project user-agent, robots.txt, a pause between requests, one client."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from sobreplano.domain.errors import FetchError
from sobreplano.domain.scraping import FetchedPage

USER_AGENT = "SobreplanoBot/0.1 (+https://github.com/afjaramillo97/sobreplano)"
DELAY_SECONDS = 2.0
TIMEOUT_SECONDS = 20.0
MAX_REDIRECTS = 3


class HttpFetcher:
    """PageFetcher over httpx.

    Every request, robots.txt included, waits DELAY_SECONDS after the previous one. robots.txt
    is read once per host and checked twice: against the requested URL before the request,
    and against the final URL after redirects. Use it as a context manager to close the client.
    """

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        # transport, sleep and monotonic are injectable so tests neither hit the network nor wait.
        self._client = httpx.Client(
            transport=transport,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=TIMEOUT_SECONDS,
        )
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None
        self._robots: dict[str, RobotFileParser] = {}

    def fetch(self, url: str) -> FetchedPage:
        """GET url and return the final URL, status and HTML.

        A non-2xx final status is returned, not raised; the caller decides what it means.

        Raises:
            FetchError: on a network error, a timeout, more than MAX_REDIRECTS redirects, or
                a URL (requested or final) that robots.txt disallows.
        """
        self._ensure_allowed(url)
        response = self._get(url)
        final_url = str(response.url)
        if final_url != url:
            # Without this a redirect could land on a path robots.txt forbids.
            self._ensure_allowed(final_url)
        return FetchedPage(
            url=final_url,
            status=response.status_code,
            html=response.text,
            fetched_at=datetime.now(UTC),
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _ensure_allowed(self, url: str) -> None:
        if not self._robots_for(url).can_fetch(USER_AGENT, url):
            raise FetchError(f"robots.txt disallows {url}")

    def _robots_for(self, url: str) -> RobotFileParser:
        origin = _origin(url)
        if origin not in self._robots:
            response = self._get(f"{origin}/robots.txt")
            parser = RobotFileParser()
            # Same reading as urllib.robotparser.read(): 401/403 forbid everything, any other
            # 4xx means no rules. A 5xx is treated as forbidding too, to stay on the safe side.
            if response.status_code in (401, 403) or response.status_code >= 500:
                parser.parse(["User-agent: *", "Disallow: /"])
            elif response.status_code < 400:
                parser.parse(response.text.splitlines())
            else:
                # An unparsed RobotFileParser forbids everything; parsing no rules allows all.
                parser.parse([])
            self._robots[origin] = parser
            # www.londonogomez.com/robots.txt redirects to londonogomez.com/robots.txt: the
            # same file answers for the final host, so it is not requested a second time.
            self._robots.setdefault(_origin(str(response.url)), parser)
        return self._robots[origin]

    def _get(self, url: str) -> httpx.Response:
        self._wait_for_turn()
        try:
            return self._client.get(url)
        except httpx.HTTPError as error:
            raise FetchError(f"GET {url} failed: {error}") from error
        finally:
            self._last_request_at = self._monotonic()

    def _wait_for_turn(self) -> None:
        if self._last_request_at is None:
            return
        remaining = DELAY_SECONDS - (self._monotonic() - self._last_request_at)
        if remaining > 0:
            self._sleep(remaining)


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"
