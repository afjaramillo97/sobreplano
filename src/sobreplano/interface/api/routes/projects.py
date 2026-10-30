"""GET /projects: project listing with the latest price and price per m² of each unit type."""

from typing import Annotated

from fastapi import APIRouter, Query

from sobreplano.domain.catalog import Municipality
from sobreplano.interface.api.dependencies import ListingQueryDep
from sobreplano.interface.api.schemas import ProjectListResponse

router = APIRouter(tags=["projects"])


@router.get("/projects")
def list_projects(
    listing_query: ListingQueryDep,
    municipality: Annotated[Municipality | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectListResponse:
    """List projects ordered by name; an unknown municipality or a bad limit gives 422."""
    page = listing_query.list_projects(municipality=municipality, limit=limit, offset=offset)
    return ProjectListResponse.from_domain(page, limit=limit, offset=offset)
