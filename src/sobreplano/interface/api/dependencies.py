"""Request-scoped dependencies: database session, listing query and the advisor use case."""

from collections.abc import Callable, Generator, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from sobreplano.application.ask_advisor import AskAdvisor
from sobreplano.domain.ports import ProjectListingQuery
from sobreplano.infrastructure.advisor.checkpointer import open_checkpointer
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery
from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.advisor_composition import build_ask_advisor


def get_session(request: Request) -> Iterator[Session]:
    """Open one session per request from the app's sessionmaker. Never commits.

    POST /advisor/chat, the only route that writes on it, commits itself; the stream opens
    its own session (get_advisor_opener).
    """
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_project_listing_query(session: SessionDep) -> ProjectListingQuery:
    """Listing query bound to the request's session."""
    return SqlProjectListingQuery(session)


ListingQueryDep = Annotated[ProjectListingQuery, Depends(get_project_listing_query)]


def get_ask_advisor(request: Request, session: SessionDep) -> Iterator[AskAdvisor]:
    """The advisor use case on the request's session and its own checkpointer connection.

    The checkpointer connection is opened per request and closed after the response; a pool
    in the lifespan is not worth it at this volume (SPEC 08).
    """
    settings: Settings = request.app.state.settings
    with open_checkpointer(settings.database_url) as checkpointer:
        yield build_ask_advisor(settings, session, checkpointer, source="api")


AskAdvisorDep = Annotated[AskAdvisor, Depends(get_ask_advisor)]


# Opens the advisor on a session and a checkpointer of its own; the caller commits.
AdvisorOpener = Callable[[], AbstractContextManager[tuple[AskAdvisor, Session]]]


def get_advisor_opener(request: Request) -> AdvisorOpener:
    """Opens the advisor use case on a new session and checkpointer, both closed on exit.

    For POST /advisor/chat/stream: its turn runs in a worker thread while the response
    streams, so it never shares the request's session. The session is yielded with the
    use case because the caller commits, also after too many tool rounds.
    """
    settings: Settings = request.app.state.settings
    session_factory: sessionmaker[Session] = request.app.state.session_factory

    @contextmanager
    def open_advisor() -> Generator[tuple[AskAdvisor, Session]]:
        with (
            session_factory() as session,
            open_checkpointer(settings.database_url) as checkpointer,
        ):
            yield build_ask_advisor(settings, session, checkpointer, source="api"), session

    return open_advisor


AdvisorOpenerDep = Annotated[AdvisorOpener, Depends(get_advisor_opener)]
