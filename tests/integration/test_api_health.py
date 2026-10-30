"""Integration test for GET /health."""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_health_is_ok_with_a_database(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
