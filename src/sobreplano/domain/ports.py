"""Ports: the repository interfaces that infrastructure implements."""

from datetime import date
from typing import Protocol
from uuid import UUID

from sobreplano.domain.catalog import Developer, Municipality, Project, UnitType
from sobreplano.domain.listings import ProjectPage
from sobreplano.domain.pricing import PriceObservation


class CatalogRepository(Protocol):
    """Storage for developers, projects and unit types. Does not commit."""

    def add_developer(self, developer: Developer) -> None: ...
    def get_developer_by_slug(self, slug: str) -> Developer | None: ...
    def add_project(self, project: Project) -> None: ...
    def get_project_by_slug(self, slug: str) -> Project | None: ...
    def add_unit_type(self, unit_type: UnitType) -> None: ...
    def list_unit_types(self, project_id: UUID) -> list[UnitType]: ...


class PriceObservationRepository(Protocol):
    """Append-only storage for price observations: add and read, never update or delete."""

    def add(self, observation: PriceObservation) -> None: ...
    def exists_for_day(self, unit_type_id: UUID, observed_on: date) -> bool: ...
    def list_by_unit_type(self, unit_type_id: UUID) -> list[PriceObservation]: ...


class ProjectListingQuery(Protocol):
    """Read-only listing of projects with the latest price of each unit type."""

    def list_projects(
        self, *, municipality: Municipality | None, limit: int, offset: int
    ) -> ProjectPage: ...
