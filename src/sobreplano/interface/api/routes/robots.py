"""GET /robots.txt: the API is not for indexing."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

ROBOTS_TXT = "User-agent: *\nDisallow: /\n"


@router.get("/robots.txt", include_in_schema=False)
def robots() -> PlainTextResponse:
    """Disallow every crawler; the public site (SPEC 11) has its own robots.txt."""
    return PlainTextResponse(ROBOTS_TXT)
