"""FastAPI app factory and lifespan."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import ValidationError

from sobreplano.infrastructure.advisor.tracing import shutdown_tracing
from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.db.rate_limit_repository import SqlRateLimitRepository
from sobreplano.infrastructure.settings import Settings, load_settings
from sobreplano.interface.api.rate_limit import RateLimiter
from sobreplano.interface.api.routes import advisor, developers, health, projects, robots


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; settings default to the environment, read when the app starts.

    The engine is created once per app, in the lifespan. Requests only open sessions from the
    sessionmaker stored in app.state.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # create_engine opens no connection, so nothing here blocks the event loop.
        resolved = settings or load_settings()
        engine = create_db_engine(resolved.database_url)
        app.state.settings = resolved
        app.state.session_factory = create_session_factory(engine)
        # Its own sessions from the same factory: counters commit apart from the request.
        app.state.rate_limiter = RateLimiter(
            SqlRateLimitRepository(app.state.session_factory), resolved
        )
        yield
        engine.dispose()
        # Send the advisor traces still buffered before the process exits.
        shutdown_tracing(resolved)

    docs_enabled = _docs_enabled(settings)
    app = FastAPI(
        title="Sobreplano",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.include_router(health.router)
    app.include_router(projects.router)
    app.include_router(developers.router)
    app.include_router(advisor.router)
    app.include_router(robots.router)
    return app


def _docs_enabled(settings: Settings | None) -> bool:
    """Whether /docs, /redoc and /openapi.json exist; these routes are fixed at build time.

    The module-level app is built at import, before DATABASE_URL need be set (tests import
    it), so an unreadable environment keeps the docs on: the app cannot start without a
    database anyway.
    """
    try:
        return (settings or load_settings()).api_docs_enabled
    except ValidationError:
        return True


app = create_app()
