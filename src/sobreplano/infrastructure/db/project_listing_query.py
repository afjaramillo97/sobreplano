"""SQLAlchemy implementation of ProjectListingQuery."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import GeoPoint, Municipality
from sobreplano.domain.listings import (
    LatestPrice,
    ProjectListing,
    ProjectPage,
    UnitTypeListing,
)
from sobreplano.infrastructure.db.geo import LAT, LON
from sobreplano.infrastructure.db.models import (
    DeveloperRow,
    PriceObservationRow,
    ProjectRow,
    UnitTypeRow,
)


class SqlProjectListingQuery:
    """Lists projects with the latest price of each unit type in at most three statements."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_projects(
        self, *, municipality: Municipality | None, limit: int, offset: int
    ) -> ProjectPage:
        """Return one page of projects ordered by name, plus the total with the filter applied.

        The unit types query is skipped when the page is empty.
        """
        total_query = select(func.count()).select_from(ProjectRow)
        page_query = (
            select(ProjectRow, DeveloperRow.name, DeveloperRow.slug, LAT, LON)
            .join(DeveloperRow, DeveloperRow.id == ProjectRow.developer_id)
            .order_by(ProjectRow.name, ProjectRow.id)
            .limit(limit)
            .offset(offset)
        )
        if municipality is not None:
            total_query = total_query.where(ProjectRow.municipality == municipality)
            page_query = page_query.where(ProjectRow.municipality == municipality)

        total = self._session.scalar(total_query) or 0
        page = self._session.execute(page_query).all()
        if not page:
            return ProjectPage(items=[], total=total)

        unit_types = self._unit_types_by_project([row.id for row, *_ in page])
        items = [
            ProjectListing(
                id=row.id,
                slug=row.slug,
                name=row.name,
                developer_name=developer_name,
                developer_slug=developer_slug,
                municipality=row.municipality,
                neighborhood=row.neighborhood,
                location=GeoPoint(lat=lat, lon=lon),
                source_url=row.source_url,
                unit_types=unit_types[row.id],
            )
            for row, developer_name, developer_slug, lat, lon in page
        ]
        return ProjectPage(items=items, total=total)

    def _unit_types_by_project(self, project_ids: list[UUID]) -> dict[UUID, list[UnitTypeListing]]:
        """Unit types of the given projects, each with its newest observation (window row 1)."""
        # Only the page's unit types enter the window, so the scan does not grow with the catalog.
        ranked = (
            select(
                PriceObservationRow.unit_type_id,
                PriceObservationRow.price_cop,
                PriceObservationRow.observed_on,
                PriceObservationRow.source,
                func.row_number()
                .over(
                    partition_by=PriceObservationRow.unit_type_id,
                    order_by=PriceObservationRow.observed_on.desc(),
                )
                .label("rank"),
            )
            .where(
                PriceObservationRow.unit_type_id.in_(
                    select(UnitTypeRow.id).where(UnitTypeRow.project_id.in_(project_ids))
                )
            )
            .subquery()
        )
        latest = (
            select(ranked.c.unit_type_id, ranked.c.price_cop, ranked.c.observed_on, ranked.c.source)
            .where(ranked.c.rank == 1)
            .subquery()
        )
        rows = self._session.execute(
            select(UnitTypeRow, latest.c.price_cop, latest.c.observed_on, latest.c.source)
            .outerjoin(latest, latest.c.unit_type_id == UnitTypeRow.id)
            .where(UnitTypeRow.project_id.in_(project_ids))
            .order_by(UnitTypeRow.name)
        )
        result: dict[UUID, list[UnitTypeListing]] = defaultdict(list)
        for row, price_cop, observed_on, source in rows:
            result[row.project_id].append(
                UnitTypeListing(
                    id=row.id,
                    name=row.name,
                    private_area_m2=row.private_area_m2,
                    built_area_m2=row.built_area_m2,
                    bedrooms=row.bedrooms,
                    bathrooms=row.bathrooms,
                    latest_price=(
                        None
                        if price_cop is None
                        else LatestPrice(
                            price_cop=price_cop, observed_on=observed_on, source=source
                        )
                    ),
                )
            )
        return result
