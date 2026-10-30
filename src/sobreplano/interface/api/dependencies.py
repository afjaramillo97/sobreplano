"""Request-scoped dependencies: database session and listing query."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from sobreplano.domain.ports import ProjectListingQuery
from sobreplano.infrastructure.db.project_listing_query import SqlProjectListingQuery


def get_session(request: Request) -> Iterator[Session]:
    """Open one session per request from the app's sessionmaker. Never commits: the API reads."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_project_listing_query(session: SessionDep) -> ProjectListingQuery:
    """Listing query bound to the request's session."""
    return SqlProjectListingQuery(session)


ListingQueryDep = Annotated[ProjectListingQuery, Depends(get_project_listing_query)]
