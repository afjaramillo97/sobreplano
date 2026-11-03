"""SQLAlchemy implementation of CatalogRepository."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from sobreplano.domain.catalog import Developer, GeoPoint, Project, UnitType
from sobreplano.infrastructure.db.geo import LAT, LON, to_geo_point, to_wkt_point
from sobreplano.infrastructure.db.models import DeveloperRow, ProjectRow, UnitTypeRow


def _to_developer(row: DeveloperRow) -> Developer:
    return Developer(id=row.id, name=row.name, slug=row.slug, website_url=row.website_url)


def _to_project(row: ProjectRow, lat: float | None, lon: float | None) -> Project:
    return Project(
        id=row.id,
        developer_id=row.developer_id,
        name=row.name,
        slug=row.slug,
        municipality=row.municipality,
        neighborhood=row.neighborhood,
        location=to_geo_point(lat, lon),
        source_url=row.source_url,
    )


def _to_unit_type(row: UnitTypeRow) -> UnitType:
    return UnitType(
        id=row.id,
        project_id=row.project_id,
        name=row.name,
        private_area_m2=row.private_area_m2,
        built_area_m2=row.built_area_m2,
        bedrooms=row.bedrooms,
        bathrooms=row.bathrooms,
    )


class SqlCatalogRepository:
    """Stores developers, projects and unit types in Postgres.

    Writes are flushed so constraint violations surface at the call site, but never committed:
    whoever opens the session decides when to commit.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_developer(self, developer: Developer) -> None:
        """Insert a developer; the slug must be unique."""
        self._session.add(
            DeveloperRow(
                id=developer.id,
                name=developer.name,
                slug=developer.slug,
                website_url=developer.website_url,
            )
        )
        self._session.flush()

    def get_developer_by_slug(self, slug: str) -> Developer | None:
        """Return the developer with this slug, or None."""
        row = self._session.scalars(
            select(DeveloperRow).where(DeveloperRow.slug == slug)
        ).one_or_none()
        return None if row is None else _to_developer(row)

    def add_project(self, project: Project) -> None:
        """Insert a project; the slug must be unique and the developer must exist."""
        self._session.add(
            ProjectRow(
                id=project.id,
                developer_id=project.developer_id,
                name=project.name,
                slug=project.slug,
                municipality=project.municipality,
                neighborhood=project.neighborhood,
                location=None if project.location is None else to_wkt_point(project.location),
                source_url=project.source_url,
            )
        )
        self._session.flush()

    def get_project_by_slug(self, slug: str) -> Project | None:
        """Return the project with this slug, or None."""
        result = self._session.execute(
            select(ProjectRow, LAT, LON).where(ProjectRow.slug == slug)
        ).one_or_none()
        return None if result is None else _to_project(*result)

    def get_project_by_source_url(self, url: str) -> Project | None:
        """Return the oldest project whose source_url is this URL, or None."""
        result = self._session.execute(
            select(ProjectRow, LAT, LON)
            .where(ProjectRow.source_url == url)
            .order_by(ProjectRow.created_at, ProjectRow.id)
            .limit(1)
        ).one_or_none()
        return None if result is None else _to_project(*result)

    def update_project_location(self, project_id: UUID, location: GeoPoint) -> None:
        """Set a project's location; used when a page publishes the map it lacked."""
        self._session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == project_id)
            .values(location=to_wkt_point(location))
        )

    def add_unit_type(self, unit_type: UnitType) -> None:
        """Insert a unit type; its name must be unique within the project."""
        self._session.add(
            UnitTypeRow(
                id=unit_type.id,
                project_id=unit_type.project_id,
                name=unit_type.name,
                private_area_m2=unit_type.private_area_m2,
                built_area_m2=unit_type.built_area_m2,
                bedrooms=unit_type.bedrooms,
                bathrooms=unit_type.bathrooms,
            )
        )
        self._session.flush()

    def list_unit_types(self, project_id: UUID) -> list[UnitType]:
        """Return the project's unit types ordered by name."""
        rows = self._session.scalars(
            select(UnitTypeRow)
            .where(UnitTypeRow.project_id == project_id)
            .order_by(UnitTypeRow.name)
        )
        return [_to_unit_type(row) for row in rows]
