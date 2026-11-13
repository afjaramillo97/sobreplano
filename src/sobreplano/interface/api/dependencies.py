"""Request-scoped dependencies: database session, listing query and the advisor use case."""

from collections.abc import Iterator
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

    Routes that write (only POST /advisor/chat) commit themselves.
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
        yield build_ask_advisor(settings, session, checkpointer)


AskAdvisorDep = Annotated[AskAdvisor, Depends(get_ask_advisor)]
