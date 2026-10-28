"""SQLAlchemy implementation of PriceObservationRepository (append-only)."""

from datetime import date
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from sobreplano.domain.pricing import PriceObservation
from sobreplano.infrastructure.db.models import PriceObservationRow


class SqlPriceObservationRepository:
    """Stores price observations in Postgres.

    There is no update or delete on purpose (constitution, principle 2); a database trigger
    enforces the same rule. Writes are flushed but never committed.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, observation: PriceObservation) -> None:
        """Insert an observation; one per unit type per observed_on day."""
        self._session.add(
            PriceObservationRow(
                id=observation.id,
                unit_type_id=observation.unit_type_id,
                price_cop=observation.price_cop,
                observed_at=observation.observed_at,
                observed_on=observation.observed_on,
                source=observation.source,
                source_url=observation.source_url,
            )
        )
        self._session.flush()

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
