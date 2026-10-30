"""The /health 503 against a real, unreachable database (no mocks)."""

from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from sobreplano.infrastructure.settings import Settings
from sobreplano.interface.api.dependencies import get_session
from sobreplano.interface.api.main import create_app

# Port 1 refuses connections at once, which raises a real OperationalError.
UNREACHABLE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:1/postgres"


def test_health_is_503_when_the_database_is_down() -> None:
    app = create_app(Settings(database_url=UNREACHABLE_URL))
    engine = create_engine(UNREACHABLE_URL)

    def unreachable_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = unreachable_session
    with TestClient(app) as client:
        response = client.get("/health")
    engine.dispose()

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
