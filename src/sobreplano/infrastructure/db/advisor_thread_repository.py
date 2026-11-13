"""SQLAlchemy implementation of AdvisorThreadRepository."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from sobreplano.infrastructure.db.models import AdvisorThreadRow


class SqlAdvisorThreadRepository:
    """Creates, counts and deletes advisor conversations. Flushes, never commits."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self) -> UUID:
        """Insert a conversation with no messages and return its id (server-generated)."""
        thread_id = uuid4()
        self._session.add(AdvisorThreadRow(id=thread_id))
        self._session.flush()
        return thread_id

    def get_turns(self, thread_id: UUID) -> int | None:
        """Messages answered so far in the conversation, or None if it does not exist."""
        return self._session.scalar(
            select(AdvisorThreadRow.turns).where(AdvisorThreadRow.id == thread_id)
        )

    def record_turn(self, thread_id: UUID) -> None:
        """Add one message to the count and set the last activity to now."""
        self._session.execute(
            update(AdvisorThreadRow)
            .where(AdvisorThreadRow.id == thread_id)
            .values(turns=AdvisorThreadRow.turns + 1, last_message_at=func.now())
        )

    def list_inactive_since(self, cutoff: datetime) -> list[UUID]:
        """Ids of conversations whose last activity is before cutoff, oldest first."""
        return list(
            self._session.scalars(
                select(AdvisorThreadRow.id)
                .where(AdvisorThreadRow.last_message_at < cutoff)
                .order_by(AdvisorThreadRow.last_message_at)
            )
        )

    def delete(self, thread_id: UUID) -> None:
        """Delete the conversation's row; its checkpoints are deleted by the caller."""
        self._session.execute(delete(AdvisorThreadRow).where(AdvisorThreadRow.id == thread_id))
