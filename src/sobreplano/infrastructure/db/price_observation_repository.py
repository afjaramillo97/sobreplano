"""SQLAlchemy implementation of PriceObservationRepository (append-only)."""

from datetime import date
from uuid import UUID

from psycopg.errors import UniqueViolation
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sobreplano.domain.errors import DuplicateObservationError
from sobreplano.domain.pricing import PriceObservation
from sobreplano.infrastructure.db.models import PriceObservationRow

ONE_PER_DAY_CONSTRAINT = "uq_price_observations_unit_type_id_observed_on"


class SqlPriceObservationRepository:
    """Stores price observations in Postgres.

    There is no update or delete on purpose (constitution, principle 2); a database trigger
    enforces the same rule. Writes are flushed but never committed.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, observation: PriceObservation) -> None:
        """Insert an observation; one per unit type per observed_on day.

        Raises:
            DuplicateObservationError: if the unit type already has one that observed_on day.
        """
        row = PriceObservationRow(
            id=observation.id,
            unit_type_id=observation.unit_type_id,
            price_cop=observation.price_cop,
            observed_at=observation.observed_at,
            observed_on=observation.observed_on,
            source=observation.source,
            source_url=observation.source_url,
        )
        # A savepoint, because a failed INSERT aborts the whole Postgres transaction otherwise
        # and the rest of the scrape run could not continue.
        try:
            with self._session.begin_nested():
                self._session.add(row)
        except IntegrityError as error:
            # Only the one-per-day rule is a duplicate; any other violation is a real bug.
            if (
                isinstance(error.orig, UniqueViolation)
                and error.orig.diag.constraint_name == ONE_PER_DAY_CONSTRAINT
            ):
                raise DuplicateObservationError(
                    f"unit type {observation.unit_type_id} already has an observation"
                    f" on {observation.observed_on}"
                ) from error
            raise

    def exists_for_day(self, unit_type_id: UUID, observed_on: date) -> bool:
        """Whether the unit type already has an observation for that day."""
        statement = select(
            exists().where(
                PriceObservationRow.unit_type_id == unit_type_id,
                PriceObservationRow.observed_on == observed_on,
            )
        )
        return bool(self._session.scalar(statement))

    def list_by_unit_type(self, unit_type_id: UUID) -> list[PriceObservation]:
        """Return the unit type's observations, oldest first."""
        rows = self._session.scalars(
            select(PriceObservationRow)
            .where(PriceObservationRow.unit_type_id == unit_type_id)
            .order_by(PriceObservationRow.observed_at)
        )
        return [
            PriceObservation(
                id=row.id,
                unit_type_id=row.unit_type_id,
                price_cop=row.price_cop,
                observed_at=row.observed_at,
                observed_on=row.observed_on,
                source=row.source,
                source_url=row.source_url,
            )
            for row in rows
        ]
