"""GET /health: liveness plus a database check."""

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from sobreplano.interface.api.dependencies import SessionDep

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health status; database tells whether SELECT 1 answered."""

    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


@router.get("/health", responses={503: {"model": HealthResponse}})
def health(session: SessionDep, response: Response) -> HealthResponse:
    """Return 200 if the database answers SELECT 1, else 503 with the same body shape."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # The 503 body is part of the contract, so no HTTPException (its body is {"detail": ...}).
        response.status_code = 503
        return HealthResponse(status="degraded", database="unavailable")
    return HealthResponse(status="ok", database="ok")
