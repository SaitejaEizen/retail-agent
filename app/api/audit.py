"""GET /audit (FR8): the audit trail, newest first. Open by design for the demo."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_clock, get_connection
from app.api.schemas import AuditEntryResponse, AuditListResponse, ErrorResponse
from app.infra.clock import Clock
from app.repositories.audit import AuditRepository
from app.services.audit_service import AuditService

router = APIRouter(tags=["audit"])


@router.get(
    "/audit",
    response_model=AuditListResponse,
    summary="List Audit Entries, newest first",
    responses={422: {"model": ErrorResponse, "description": "Invalid query parameter"}},
)
def list_audit(
    conn: Annotated[sqlite3.Connection, Depends(get_connection)],
    clock: Annotated[Clock, Depends(get_clock)],
    order_id: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
) -> AuditListResponse:
    entries = AuditService(conn, AuditRepository(conn, clock)).list_entries(order_id)
    return AuditListResponse(
        entries=[
            AuditEntryResponse(
                id=entry.id,
                created_at=entry.created_at,
                action=entry.action.value,
                outcome=entry.outcome.value,
                order_id=entry.order_id,
                masked_email=entry.masked_email,
                details=dict(entry.details),
            )
            for entry in entries
        ]
    )
