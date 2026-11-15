"""Rate limits per client IP and group of routes: 429 with Retry-After, counted in Postgres."""

import hashlib
import hmac
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from sobreplano.domain.errors import RateLimitStoreError
from sobreplano.domain.ports import RateLimitRepository
from sobreplano.domain.rate_limit import Limit, check_limit, windows_at
from sobreplano.infrastructure.settings import Settings

logger = logging.getLogger(__name__)

# Development only: production sets RATE_LIMIT_KEY (SPEC 12). A fixed key keeps the hashes
# stable between restarts, but anyone who reads this file can reverse them.
DEVELOPMENT_KEY = b"sobreplano-development-rate-limit-key"
CLIENT_KEY_LENGTH = 32
UNKNOWN_CLIENT = "unknown"


class Bucket(StrEnum):
    """Groups of routes that share a limit."""

    LIST = "list"
    DETAIL = "detail"
    ADVISOR = "advisor"


# Each advisor message costs money, so the advisor is refused when the counters are down.
FAIL_CLOSED = frozenset({Bucket.ADVISOR})


def limits_from(settings: Settings) -> dict[Bucket, Limit]:
    """The limit of each group of routes, from the settings."""
    return {
        Bucket.LIST: Limit(settings.rate_limit_list_per_minute, settings.rate_limit_list_per_day),
        Bucket.DETAIL: Limit(
            settings.rate_limit_detail_per_minute, settings.rate_limit_detail_per_day
        ),
        Bucket.ADVISOR: Limit(
            settings.rate_limit_advisor_per_minute, settings.rate_limit_advisor_per_day
        ),
    }


def client_ip(client_host: str | None, forwarded_for: str | None, trusted_hops: int) -> str:
    """The IP to limit: the socket peer, or with trusted proxies the X-Forwarded-For entry
    that many hops from the right.

    Each trusted proxy appends the address it received the request from, so the entry at
    trusted_hops from the right is the client as the outermost trusted proxy saw it; entries
    to its left can be forged by the client. With fewer entries than hops the header is not
    what the proxies would write, so the socket peer is used.
    """
    if trusted_hops > 0 and forwarded_for:
        entries = [entry.strip() for entry in forwarded_for.split(",") if entry.strip()]
        if len(entries) >= trusted_hops:
            return entries[-trusted_hops]
    return client_host or UNKNOWN_CLIENT


class RateLimiter:
    """Counts each request and raises 429 when its client goes over its group's limit."""

    def __init__(
        self,
        repository: RateLimitRepository,
        settings: Settings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._enabled = settings.rate_limits_enabled
        self._trusted_hops = settings.trusted_proxy_hops
        self._clock = clock
        self._limits = limits_from(settings)
        if settings.rate_limit_key is None or not settings.rate_limit_key.get_secret_value():
            if self._enabled:
                logger.warning("RATE_LIMIT_KEY is not set: client hashes use the development key")
            self._key = DEVELOPMENT_KEY
        else:
            self._key = settings.rate_limit_key.get_secret_value().encode()

    def client_key(self, ip: str) -> str:
        """HMAC-SHA256 of the IP with the secret key, hex, cut to 32 characters.

        A plain hash of an IPv4 is reversed by trying all 2^32 of them; the key prevents it.
        """
        digest = hmac.new(self._key, ip.encode(), hashlib.sha256).hexdigest()
        return digest[:CLIENT_KEY_LENGTH]

    def check(self, bucket: Bucket, request: Request) -> None:
        """Count this request for its client and let it through, or refuse it.

        Raises:
            HTTPException: 429 with Retry-After when a window's limit is exceeded; 503 when
                the counters are down and the group fails closed (the advisor).
        """
        if not self._enabled:
            return
        ip = client_ip(
            request.client.host if request.client else None,
            request.headers.get("x-forwarded-for"),
            self._trusted_hops,
        )
        key = self.client_key(ip)
        now = self._clock()
        windows = windows_at(now)
        try:
            counts = self._repository.hit(bucket, key, windows.minute_start, windows.day_start)
        except RateLimitStoreError as error:
            if bucket in FAIL_CLOSED:
                logger.error("rate limit store down, refusing bucket=%s: %s", bucket, error)
                raise HTTPException(503, detail="service unavailable") from error
            logger.error("rate limit store down, serving bucket=%s: %s", bucket, error)
            return
        exceeded = check_limit(counts, self._limits[bucket], windows, now)
        if exceeded is None:
            return
        logger.warning(
            "rate_limited bucket=%s window=%s client=%s", bucket, exceeded.window, key[:8]
        )
        raise HTTPException(
            429,
            detail="too many requests",
            headers={"Retry-After": str(exceeded.retry_after_seconds)},
        )


def get_rate_limiter(request: Request) -> RateLimiter:
    """The app's limiter, built once in the lifespan."""
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def limit_list(request: Request, limiter: RateLimiterDep) -> None:
    """Rate limit of GET /projects and GET /developers."""
    limiter.check(Bucket.LIST, request)


def limit_detail(request: Request, limiter: RateLimiterDep) -> None:
    """Rate limit of GET /projects/{slug}, the narrowest: it returns the price history."""
    limiter.check(Bucket.DETAIL, request)


def limit_advisor(request: Request, limiter: RateLimiterDep) -> None:
    """Rate limit of POST /advisor/chat."""
    limiter.check(Bucket.ADVISOR, request)


ListRateLimitDep = Annotated[None, Depends(limit_list)]
DetailRateLimitDep = Annotated[None, Depends(limit_detail)]
AdvisorRateLimitDep = Annotated[None, Depends(limit_advisor)]
