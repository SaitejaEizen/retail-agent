"""GET /healthz (FR9)."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_connection
from app.api.schemas import ErrorResponse, HealthResponse
from app.repositories.health import HealthRepository
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get(
    "/healthz",
    response_model=HealthResponse,
    summary="Service and database health",
    responses={503: {"model": ErrorResponse, "description": "Database unavailable"}},
)
def healthz(conn: Annotated[sqlite3.Connection, Depends(get_connection)]) -> HealthResponse:
    HealthService(HealthRepository(conn)).check()
    return HealthResponse(status="ok", database="ok")
