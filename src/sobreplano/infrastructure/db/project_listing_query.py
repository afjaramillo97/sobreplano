"""SQLAlchemy implementation of ProjectListingQuery: filters, sort and price windows."""

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Label,
    Subquery,
    cast,
    func,
    null,
    nulls_last,
    select,
)
from sqlalchemy.orm import InstrumentedAttribute, Session

from sobreplano.domain.listings import (
    LatestPrice,
    PricePoint,
    ProjectFilters,
    ProjectListing,
    ProjectPage,
    ProjectSort,
    UnitTypeListing,
)
from sobreplano.infrastructure.db.geo import LAT, LON, to_geo_point
from sobreplano.infrastructure.db.models import (
    DeveloperRow,
    PriceObservationRow,
    ProjectRow,
    UnitTypeRow,
)


class SqlProjectListingQuery:
    """Lists projects with the latest and first price of each unit type, in at most 3 statements."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_projects(
        self, *, filters: ProjectFilters, sort: ProjectSort, limit: int, offset: int
    ) -> ProjectPage:
        """Return one page of projects plus the total that match, ignoring pagination.

        A project matches when one unit type meets every unit type filter at once, and the
        response carries only those unit types. The unit types query is skipped when the page
        is empty.
        """
        by_price = sort == ProjectSort.PRICE
        has_unit_filters = _has_unit_type_filters(filters)

        project_conditions = _project_conditions(filters)
        count_query = (
            select(func.count())
            .select_from(ProjectRow)
            .join(DeveloperRow)
            .where(*project_conditions)
        )
        page_query = (
            select(ProjectRow, DeveloperRow.name, DeveloperRow.slug, LAT, LON)
            .join(DeveloperRow)
            .where(*project_conditions)
        )
        if has_unit_filters:
            counted = self._matching_projects(filters, with_price=False)
            count_query = count_query.join(counted, counted.c.project_id == ProjectRow.id)
        if by_price or has_unit_filters:
            matching = self._matching_projects(filters, with_price=by_price)
            # Inner join: only projects with a matching unit type. Outer join when sorting
            # without unit type filters, so projects without unit types or prices go last.
            page_query = (
                page_query.join(matching, matching.c.project_id == ProjectRow.id)
                if has_unit_filters
                else page_query.outerjoin(matching, matching.c.project_id == ProjectRow.id)
            )
            if by_price:
                page_query = page_query.order_by(nulls_last(matching.c.min_price.asc()))
        page_query = page_query.order_by(ProjectRow.name, ProjectRow.id).limit(limit).offset(offset)

        total = self._session.scalar(count_query) or 0
        page = self._session.execute(page_query).all()
        if not page:
            return ProjectPage(items=[], total=total)

        unit_types = self._unit_types_by_project([row.id for row, *_ in page], filters)
        items = [
            ProjectListing(
                id=row.id,
                slug=row.slug,
                name=row.name,
                developer_name=developer_name,
                developer_slug=developer_slug,
                municipality=row.municipality,
                neighborhood=row.neighborhood,
                location=to_geo_point(lat, lon),
                source_url=row.source_url,
                unit_types=unit_types[row.id],
            )
            for row, developer_name, developer_slug, lat, lon in page
        ]
        return ProjectPage(items=items, total=total)

    @staticmethod
    def _latest_prices(project_ids: list[UUID] | None) -> Subquery:
        """Newest and oldest observation of each unit type, one row per unit type.

        With project_ids, only the unit types of those projects enter the window, so the scan
        does not grow with the catalog; None scans every observation (price filters and sort).
        """
        unit_type_id = PriceObservationRow.unit_type_id

        def first_of(column: InstrumentedAttribute[Any], label: str) -> Label[Any]:
            # Without a frame, the default one starts at the partition's first row, so this is
            # always the oldest observation. type_ keeps the enum conversion of `source`.
            return (
                func.first_value(column, type_=column.type)
                .over(partition_by=unit_type_id, order_by=PriceObservationRow.observed_on)
                .label(label)
            )

        ranked = select(
            PriceObservationRow.unit_type_id,
            PriceObservationRow.price_cop,
            PriceObservationRow.observed_on,
            PriceObservationRow.source,
            func.row_number()
            .over(partition_by=unit_type_id, order_by=PriceObservationRow.observed_on.desc())
            .label("rank"),
            first_of(PriceObservationRow.price_cop, "first_price_cop"),
            first_of(PriceObservationRow.observed_on, "first_on"),
            first_of(PriceObservationRow.source, "first_source"),
        )
        if project_ids is not None:
            ranked = ranked.where(
                PriceObservationRow.unit_type_id.in_(
                    select(UnitTypeRow.id).where(UnitTypeRow.project_id.in_(project_ids))
                )
            )
        ranked_sq = ranked.subquery()
        return (
            select(
                ranked_sq.c.unit_type_id,
                ranked_sq.c.price_cop,
                ranked_sq.c.observed_on,
                ranked_sq.c.source,
                ranked_sq.c.first_price_cop,
                ranked_sq.c.first_on,
                ranked_sq.c.first_source,
            )
            .where(ranked_sq.c.rank == 1)
            .subquery()
        )

    def _matching_projects(self, filters: ProjectFilters, *, with_price: bool) -> Subquery:
        """One row per project that has a unit type meeting the filters, with min_price.

        min_price is the lowest latest price among those unit types (NULL if none has a price);
        it is only computed when asked for, because it needs a scan of all observations.
        """
        query = select(UnitTypeRow.project_id)
        if with_price or filters.min_price is not None or filters.max_price is not None:
            latest = self._latest_prices(None)
            query = query.outerjoin(latest, latest.c.unit_type_id == UnitTypeRow.id)
            conditions = _unit_type_conditions(filters, latest.c.price_cop)
            query = query.add_columns(func.min(latest.c.price_cop).label("min_price"))
        else:
            conditions = _unit_type_conditions(filters, None)
            query = query.add_columns(cast(null(), BigInteger).label("min_price"))
        return query.where(*conditions).group_by(UnitTypeRow.project_id).subquery()

    def _unit_types_by_project(
        self, project_ids: list[UUID], filters: ProjectFilters
    ) -> dict[UUID, list[UnitTypeListing]]:
        """Unit types of the given projects that meet the filters, with latest and first price."""
        latest = self._latest_prices(project_ids)
        rows = self._session.execute(
            select(
                UnitTypeRow,
                latest.c.price_cop,
                latest.c.observed_on,
                latest.c.source,
                latest.c.first_price_cop,
                latest.c.first_on,
                latest.c.first_source,
            )
            .outerjoin(latest, latest.c.unit_type_id == UnitTypeRow.id)
            .where(UnitTypeRow.project_id.in_(project_ids))
            .where(*_unit_type_conditions(filters, latest.c.price_cop))
            .order_by(UnitTypeRow.name)
        )
        result: dict[UUID, list[UnitTypeListing]] = defaultdict(list)
        for row, price_cop, observed_on, source, first_cop, first_on, first_source in rows:
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
                    first_price=(
                        None
                        if first_cop is None
                        else PricePoint(
                            observed_on=first_on, price_cop=first_cop, source=first_source
                        )
                    ),
                )
            )
        return result


def _has_unit_type_filters(filters: ProjectFilters) -> bool:
    """True if any filter applies to a unit type rather than to the project."""
    return any(
        value is not None
        for value in (
            filters.min_price,
            filters.max_price,
            filters.min_bedrooms,
            filters.min_area,
            filters.max_area,
        )
    )


def _unit_type_conditions(
    filters: ProjectFilters, latest_price: ColumnElement[int] | None
) -> list[ColumnElement[bool]]:
    """WHERE clauses for the unit type filters; a NULL value never meets a filter on it.

    The area is the base area of price_per_m2_cop: private if known, else built.
    """
    base_area = func.coalesce(UnitTypeRow.private_area_m2, UnitTypeRow.built_area_m2)
    conditions: list[ColumnElement[bool]] = []
    if filters.min_bedrooms is not None:
        conditions.append(UnitTypeRow.bedrooms >= filters.min_bedrooms)
    if filters.min_area is not None:
        conditions.append(base_area >= filters.min_area)
    if filters.max_area is not None:
        conditions.append(base_area <= filters.max_area)
    if latest_price is not None:
        if filters.min_price is not None:
            conditions.append(latest_price >= filters.min_price)
        if filters.max_price is not None:
            conditions.append(latest_price <= filters.max_price)
    return conditions


def _project_conditions(filters: ProjectFilters) -> list[ColumnElement[bool]]:
    """WHERE clauses for the project level filters: municipality and developer slug."""
    conditions: list[ColumnElement[bool]] = []
    if filters.municipality is not None:
        conditions.append(ProjectRow.municipality == filters.municipality)
    if filters.developer is not None:
        conditions.append(DeveloperRow.slug == filters.developer)
    return conditions
