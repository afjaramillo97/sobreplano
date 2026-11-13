"""SQLAlchemy implementation of LlmUsageRepository."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sobreplano.domain.advisor import LlmCall
from sobreplano.infrastructure.db.models import LlmUsageRow

BOGOTA = ZoneInfo("America/Bogota")


class SqlLlmUsageRepository:
    """Appends LLM calls and sums their cost per day. Flushes, never commits."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, feature: str, call: LlmCall, thread_id: UUID | None) -> None:
        """Insert one call; the table's CHECK rejects an unknown feature."""
        self._session.add(
            LlmUsageRow(
                id=uuid4(),
                feature=feature,
                thread_id=thread_id,
                model=call.model,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cost_usd=call.cost_usd,
            )
        )
        self._session.flush()

    def cost_on(self, feature: str, day: date) -> Decimal:
        """Total cost in USD of a feature's calls on day (America/Bogota); 0 if none.

        Calls of models without a price (cost NULL) add nothing.
        """
        # A half-open range on created_at instead of casting it, so the index can be used.
        start = datetime.combine(day, time.min, tzinfo=BOGOTA)
        total = self._session.scalar(
            select(func.coalesce(func.sum(LlmUsageRow.cost_usd), 0)).where(
                LlmUsageRow.feature == feature,
                LlmUsageRow.created_at >= start,
                LlmUsageRow.created_at < start + timedelta(days=1),
            )
        )
        return Decimal(total or 0)
