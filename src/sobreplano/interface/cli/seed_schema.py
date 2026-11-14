"""Pydantic schema of seeds/projects.json, validated before anything touches the database."""

from decimal import Decimal
from itertools import pairwise
from typing import Annotated, Self
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from sobreplano.domain.catalog import Developer, GeoPoint, Municipality, Project, UnitType

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
Url = Annotated[str, StringConstraints(pattern=r"^https?://\S+$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class _Strict(BaseModel):
    """Base for seed models: unknown fields are typos, so they are errors."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SeedDeveloper(_Strict):
    """A developer as written in the seed file."""

    name: Name
    slug: Slug
    website_url: Url


class SeedObservation(_Strict):
    """The manually copied price of one unit type and the public page it came from."""

    price_cop: Annotated[int, Field(gt=0)]
    observed_at: AwareDatetime
    source_url: Url


class SeedUnitType(_Strict):
    """A unit type with its latest manual price observation and, optionally, earlier ones."""

    name: Name
    private_area_m2: Decimal | None = None
    built_area_m2: Decimal | None = None
    bedrooms: Annotated[int, Field(ge=0)]
    bathrooms: Annotated[int, Field(ge=0)]
    # None for a unit type the developer lists without a price.
    observation: SeedObservation | None = None
    # Observations before `observation`, oldest first (the evals catalog uses it).
    history: list[SeedObservation] = []

    @model_validator(mode="after")
    def _build_once_to_validate(self) -> Self:
        # Reuse the domain rules (areas) instead of copying them here.
        self.to_unit_type(uuid4())
        if self.history and self.observation is None:
            raise ValueError(f"unit type {self.name!r} has history but no observation")
        dates = [o.observed_at for o in self.history]
        if self.observation is not None:
            dates.append(self.observation.observed_at)
        if any(earlier >= later for earlier, later in pairwise(dates)):
            raise ValueError(f"observations of unit type {self.name!r} are not in date order")
        return self

    def observations(self) -> list[SeedObservation]:
        """History and latest observation, oldest first."""
        return [*self.history, *([self.observation] if self.observation is not None else [])]

    def to_unit_type(self, project_id: UUID) -> UnitType:
        """Build the domain entity with a fresh id.

        Raises:
            DomainValidationError: if the areas break the domain rules.
        """
        return UnitType(
            id=uuid4(),
            project_id=project_id,
            name=self.name,
            private_area_m2=self.private_area_m2,
            built_area_m2=self.built_area_m2,
            bedrooms=self.bedrooms,
            bathrooms=self.bathrooms,
        )


class SeedProject(_Strict):
    """A project with its developer and unit types."""

    developer: SeedDeveloper
    name: Name
    slug: Slug
    municipality: Municipality
    neighborhood: str | None = None
    # Both or neither: None while the developer publishes no map.
    lat: float | None = None
    lon: float | None = None
    source_url: Url
    unit_types: Annotated[list[SeedUnitType], Field(min_length=1)]

    @model_validator(mode="after")
    def _validate_location_and_names(self) -> Self:
        if (self.lat is None) != (self.lon is None):
            raise ValueError(f"project {self.slug!r} needs both lat and lon, or neither")
        # GeoPoint holds the Aburrá Valley range check; building it raises on swapped lat/lon.
        self.location()
        names = [unit_type.name for unit_type in self.unit_types]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate unit type names in project {self.slug!r}")
        return self

    def location(self) -> GeoPoint | None:
        """The project's point, or None when the seed gives no coordinates."""
        if self.lat is None or self.lon is None:
            return None
        return GeoPoint(lat=self.lat, lon=self.lon)

    def to_developer(self) -> Developer:
        """Build the domain developer with a fresh id."""
        return Developer(
            id=uuid4(),
            name=self.developer.name,
            slug=self.developer.slug,
            website_url=self.developer.website_url,
        )

    def to_project(self, developer_id: UUID) -> Project:
        """Build the domain project with a fresh id."""
        return Project(
            id=uuid4(),
            developer_id=developer_id,
            name=self.name,
            slug=self.slug,
            municipality=self.municipality,
            neighborhood=self.neighborhood,
            location=self.location(),
            source_url=self.source_url,
        )


class SeedFile(_Strict):
    """The whole seed file."""

    projects: Annotated[list[SeedProject], Field(min_length=1)]

    @model_validator(mode="after")
    def _unique_slugs(self) -> Self:
        project_slugs = [project.slug for project in self.projects]
        if len(set(project_slugs)) != len(project_slugs):
            raise ValueError("duplicate project slugs")
        # A developer may appear in several projects, but only with the same data.
        developers: dict[str, SeedDeveloper] = {}
        for project in self.projects:
            known = developers.setdefault(project.developer.slug, project.developer)
            if known != project.developer:
                raise ValueError(f"developer {known.slug!r} is described differently twice")
        return self
