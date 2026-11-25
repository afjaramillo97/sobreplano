"""FastAPI app factory and lifespan."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

    startup = _startup_settings(settings)
    docs_enabled = startup is None or startup.api_docs_enabled
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
    if startup is not None and startup.cors_allowed_origins:
        # GET for the reads and POST with a JSON body for the advisor (SPEC 11c). The
        # middleware answers the preflight itself, so it never counts against a limit.
        # Without expose_headers a browser cannot read Retry-After on a 429.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=startup.cors_allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            allow_credentials=False,
            expose_headers=["Retry-After"],
        )
    return app


def _startup_settings(settings: Settings | None) -> Settings | None:
    """Settings for what is fixed when the app is built: the docs routes and CORS.

    The module-level app is built at import, before DATABASE_URL need be set (tests import
    it), so an unreadable environment gives None: docs on and no CORS. The app cannot start
    without a database anyway.
    """
    try:
        return settings or load_settings()
    except ValidationError:
        return None


app = create_app()
