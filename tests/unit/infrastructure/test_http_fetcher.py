"""Unit tests for HttpFetcher, over httpx.MockTransport: no network, no real waiting."""

from collections.abc import Callable

import httpx
import pytest

from sobreplano.domain.errors import FetchError
from sobreplano.infrastructure.scraping.http_fetcher import USER_AGENT, HttpFetcher

ROBOTS = "User-agent: *\nDisallow: /admin/\n"
Handler = Callable[[httpx.Request], httpx.Response]


class FakeClock:
    """monotonic() and sleep() that only move when told to."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def site(robots: httpx.Response | None = None) -> tuple[Handler, list[httpx.Request]]:
    """A fake londonogomez.com: www redirects to the bare host, /node/1 to its canonical page."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        url = request.url
        if url.host == "www.londonogomez.com":
            return httpx.Response(301, headers={"Location": f"https://londonogomez.com{url.path}"})
        if url.path == "/robots.txt":
            return robots or httpx.Response(200, text=ROBOTS)
        if url.path == "/node/1":
            return httpx.Response(301, headers={"Location": "/proyectos-vivienda/x/y"})
        if url.path == "/node/2":
            return httpx.Response(301, headers={"Location": "/admin/secret"})
        if url.path == "/loop":
            return httpx.Response(302, headers={"Location": "/loop"})
        if url.path == "/missing":
            return httpx.Response(404, text="not found")
        return httpx.Response(200, text=f"<html>{url.path}</html>")

    return handler, requests


def make_fetcher(handler: Handler, clock: FakeClock | None = None) -> HttpFetcher:
    clock = clock or FakeClock()
    return HttpFetcher(
        transport=httpx.MockTransport(handler), sleep=clock.sleep, monotonic=clock.monotonic
    )


def test_follows_redirects_and_returns_the_final_url() -> None:
    handler, _ = site()
    page = make_fetcher(handler).fetch("https://londonogomez.com/node/1")
    assert page.url == "https://londonogomez.com/proyectos-vivienda/x/y"
    assert page.status == 200
    assert page.html == "<html>/proyectos-vivienda/x/y</html>"
    assert page.fetched_at.tzinfo is not None


def test_every_request_carries_the_project_user_agent() -> None:
    handler, requests = site()
    make_fetcher(handler).fetch("https://londonogomez.com/node/1")
    assert {r.headers["User-Agent"] for r in requests} == {USER_AGENT}


def test_robots_is_read_once_per_host() -> None:
    handler, requests = site()
    fetcher = make_fetcher(handler)
    fetcher.fetch("https://londonogomez.com/a")
    fetcher.fetch("https://londonogomez.com/b")
    assert [r.url.path for r in requests] == ["/robots.txt", "/a", "/b"]


def test_waits_two_seconds_between_every_request_robots_included() -> None:
    handler, _ = site()
    clock = FakeClock()
    fetcher = make_fetcher(handler, clock)
    fetcher.fetch("https://londonogomez.com/a")
    fetcher.fetch("https://londonogomez.com/b")
    # robots.txt, then /a after 2 s, then /b after 2 s.
    assert clock.sleeps == [2.0, 2.0]


def test_does_not_wait_when_enough_time_has_passed() -> None:
    handler, _ = site()
    clock = FakeClock()
    fetcher = make_fetcher(handler, clock)
    fetcher.fetch("https://londonogomez.com/a")
    clock.now += 5
    fetcher.fetch("https://londonogomez.com/b")
    assert clock.sleeps == [2.0]


def test_disallowed_url_is_never_requested() -> None:
    handler, requests = site()
    with pytest.raises(FetchError, match=r"robots\.txt"):
        make_fetcher(handler).fetch("https://londonogomez.com/admin/x")
    assert [r.url.path for r in requests] == ["/robots.txt"]


def test_redirect_to_a_disallowed_url_is_refused() -> None:
    handler, _ = site()
    with pytest.raises(FetchError, match="/admin/secret"):
        make_fetcher(handler).fetch("https://londonogomez.com/node/2")


def test_robots_is_checked_against_the_final_host() -> None:
    handler, requests = site()
    page = make_fetcher(handler).fetch("https://www.londonogomez.com/a")
    assert page.url == "https://londonogomez.com/a"
    # www's robots.txt redirects to the final host's file, which then covers the final URL.
    robots_hosts = [r.url.host for r in requests if r.url.path == "/robots.txt"]
    assert robots_hosts == ["www.londonogomez.com", "londonogomez.com"]


def test_too_many_redirects_is_a_fetch_error() -> None:
    handler, requests = site()
    with pytest.raises(FetchError):
        make_fetcher(handler).fetch("https://londonogomez.com/loop")
    # One request plus at most three redirects, after robots.txt.
    assert len([r for r in requests if r.url.path == "/loop"]) == 4


def test_non_2xx_status_is_returned_not_raised() -> None:
    handler, _ = site()
    assert make_fetcher(handler).fetch("https://londonogomez.com/missing").status == 404


def test_network_error_is_a_fetch_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(FetchError, match="timed out"):
        make_fetcher(handler).fetch("https://londonogomez.com/a")


@pytest.mark.parametrize(
    ("status", "allowed"), [(404, True), (403, False), (401, False), (503, False)]
)
def test_robots_status_codes(status: int, allowed: bool) -> None:
    handler, _ = site(robots=httpx.Response(status))
    fetcher = make_fetcher(handler)
    if allowed:
        assert fetcher.fetch("https://londonogomez.com/a").status == 200
    else:
        with pytest.raises(FetchError, match=r"robots\.txt"):
            fetcher.fetch("https://londonogomez.com/a")
