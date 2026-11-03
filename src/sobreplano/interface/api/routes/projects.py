"""GET /projects and GET /projects/{slug}: search with filters, and one project with history."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query

from sobreplano.domain.catalog import Municipality
from sobreplano.domain.errors import DomainValidationError
from sobreplano.domain.listings import ProjectFilters, ProjectSort
from sobreplano.interface.api.dependencies import ListingQueryDep
from sobreplano.interface.api.schemas import ProjectDetailOut, ProjectListResponse

router = APIRouter(tags=["projects"])


@router.get("/projects")
def list_projects(
    listing_query: ListingQueryDep,
    municipality: Annotated[Municipality | None, Query()] = None,
    developer: Annotated[str | None, Query(description="Developer slug; unknown gives []")] = None,
    min_price: Annotated[int | None, Query(gt=0, description="COP, latest price")] = None,
    max_price: Annotated[int | None, Query(gt=0, description="COP, latest price")] = None,
    min_bedrooms: Annotated[int | None, Query(gt=0)] = None,
    min_area: Annotated[Decimal | None, Query(gt=0, description="m², private else built")] = None,
    max_area: Annotated[Decimal | None, Query(gt=0, description="m², private else built")] = None,
    sort: Annotated[ProjectSort, Query()] = ProjectSort.NAME,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectListResponse:
    """Search projects; one unit type must meet every price, bedroom and area filter at once.

    Each project carries only the unit types that meet them. A bad value, an unknown
    municipality, or a minimum above its maximum gives 422.
    """
    try:
        filters = ProjectFilters(
            municipality=municipality,
            developer=developer,
            min_price=min_price,
            max_price=max_price,
            min_bedrooms=min_bedrooms,
            min_area=min_area,
            max_area=max_area,
        )
    except DomainValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    page = listing_query.list_projects(filters=filters, sort=sort, limit=limit, offset=offset)
    return ProjectListResponse.from_domain(page, limit=limit, offset=offset)


@router.get("/projects/{slug}")
def get_project(
    listing_query: ListingQueryDep,
    slug: Annotated[str, Path(pattern="^[a-z0-9-]{1,80}$")],
) -> ProjectDetailOut:
    """Return a project with all its unit types and their price history; 404 if unknown."""
    detail = listing_query.get_project(slug)
    if detail is None:
        raise HTTPException(status_code=404, detail="project not found")
    return ProjectDetailOut.from_domain(detail)
