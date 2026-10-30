"""FastAPI app factory and lifespan."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from sobreplano.infrastructure.db.engine import create_db_engine, create_session_factory
from sobreplano.infrastructure.settings import Settings, load_settings
from sobreplano.interface.api.routes import health


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the app; settings default to the environment, read when the app starts.

    The engine is created once per app, in the lifespan. Requests only open sessions from the
    sessionmaker stored in app.state.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        # create_engine opens no connection, so nothing here blocks the event loop.
        engine = create_db_engine((settings or load_settings()).database_url)
        app.state.session_factory = create_session_factory(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Sobreplano", lifespan=lifespan)
    app.include_router(health.router)
    return app


app = create_app()
