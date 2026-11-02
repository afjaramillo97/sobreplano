"""SQLAlchemy implementation of ScrapeRunRepository."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from sobreplano.domain.scraping import ExtractionResult, ScrapedPage, ScrapeRun, ScrapeRunStatus
from sobreplano.infrastructure.db.models import PageExtractionRow, ScrapedPageRow, ScrapeRunRow
from sobreplano.infrastructure.scraping.extraction_schema import ExtractedProject


class SqlScrapeRunRepository:
    """Stores scrape runs, their pages and reusable extractions. Flushes, never commits."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def try_lock(self, developer_id: UUID) -> bool:
        """Try the developer's advisory lock; True if taken, False if another run holds it.

        A transaction-level lock (released at commit or rollback), because the Supabase
        pooler in transaction mode does not keep session state between transactions.
        """
        return bool(
            self._session.scalar(select(func.pg_try_advisory_xact_lock(_lock_key(developer_id))))
        )

    def has_succeeded(self, developer_id: UUID, run_on: date) -> bool:
        """True if a run of this developer on run_on ended SUCCEEDED (committed runs only)."""
        return bool(
            self._session.scalar(
                select(
                    exists().where(
                        ScrapeRunRow.developer_id == developer_id,
                        ScrapeRunRow.run_on == run_on,
                        ScrapeRunRow.status == ScrapeRunStatus.SUCCEEDED,
                    )
                )
            )
        )

    def start(self, developer_id: UUID, run_on: date) -> ScrapeRun:
        """Insert a RUNNING run started now and return it."""
        run = ScrapeRun(
            id=uuid4(),
            developer_id=developer_id,
            run_on=run_on,
            started_at=datetime.now(UTC),
            status=ScrapeRunStatus.RUNNING,
        )
        self._session.add(
            ScrapeRunRow(
                id=run.id,
                developer_id=run.developer_id,
                run_on=run.run_on,
                started_at=run.started_at,
                status=run.status,
            )
        )
        self._session.flush()
        return run

    def record_page(self, run_id: UUID, page: ScrapedPage) -> None:
        """Insert a scraped page; one row per canonical URL per run."""
        self._session.add(
            ScrapedPageRow(
                id=uuid4(),
                scrape_run_id=run_id,
                url=page.url,
                http_status=page.http_status,
                content_sha256=page.content_sha256,
                storage_key=page.storage_key,
                fetched_at=page.fetched_at,
            )
        )
        self._session.flush()

    def find_extraction(self, content_sha256: str, model: str) -> ExtractionResult | None:
        """The stored extraction of this HTML by this model, or None."""
        row = self._session.scalars(
            select(PageExtractionRow).where(
                PageExtractionRow.content_sha256 == content_sha256,
                PageExtractionRow.model == model,
            )
        ).one_or_none()
        if row is None:
            return None
        return ExtractionResult(
            model=row.model,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            project=ExtractedProject.model_validate(row.payload).to_domain(),
        )

    def save_extraction(self, content_sha256: str, result: ExtractionResult) -> None:
        """Store an extraction; if the same HTML and model are already stored, keep the first."""
        payload = ExtractedProject.from_domain(result.project).model_dump(mode="json")
        # DO NOTHING instead of an error: a concurrent run may have stored the same extraction.
        self._session.execute(
            insert(PageExtractionRow)
            .values(
                id=uuid4(),
                content_sha256=content_sha256,
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                payload=payload,
            )
            .on_conflict_do_nothing(index_elements=["content_sha256", "model"])
        )

    def finish(self, run: ScrapeRun) -> None:
        """Write the run's final status, counters, finish time and error."""
        self._session.execute(
            update(ScrapeRunRow)
            .where(ScrapeRunRow.id == run.id)
            .values(
                status=run.status,
                finished_at=run.finished_at,
                pages_fetched=run.pages_fetched,
                pages_failed=run.pages_failed,
                observations_recorded=run.observations_recorded,
                error=run.error,
            )
        )


def _lock_key(developer_id: UUID) -> int:
    # Advisory locks take a bigint: the UUID's first 8 bytes, as a signed 64-bit integer.
    return int.from_bytes(developer_id.bytes[:8], "big", signed=True)
