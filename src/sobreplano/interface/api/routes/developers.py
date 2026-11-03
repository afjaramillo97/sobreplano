"""GET /developers: the developers with their number of projects."""

from fastapi import APIRouter

from sobreplano.interface.api.dependencies import ListingQueryDep
from sobreplano.interface.api.schemas import DeveloperSummaryOut

router = APIRouter(tags=["developers"])


@router.get("/developers")
def list_developers(listing_query: ListingQueryDep) -> list[DeveloperSummaryOut]:
    """List developers ordered by name; the slug is what `GET /projects?developer=` takes."""
    return [DeveloperSummaryOut.from_domain(summary) for summary in listing_query.list_developers()]
