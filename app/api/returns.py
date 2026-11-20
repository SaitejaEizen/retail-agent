"""POST /returns (FR3–FR6). Email travels only in the body (AD-9)."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_clock, get_connection
from app.api.schemas import (
    ErrorResponse,
    ReturnLineResponse,
    ReturnRequest,
    ReturnResponse,
    ReturnSummary,
)
from app.domain.models import Return
from app.infra.clock import Clock
from app.services.return_service import ReturnService

router = APIRouter(tags=["returns"])


def _lines(ret: Return) -> list[ReturnLineResponse]:
    return [
        ReturnLineResponse(
            line_id=line.line_id,
            sku=line.sku,
            quantity=line.quantity,
            refund_cents=line.refund_cents,
        )
        for line in ret.lines
    ]


def to_return_summary(ret: Return) -> ReturnSummary:
    return ReturnSummary(
        return_id=ret.return_id,
        created_at=ret.created_at,
        reason=ret.reason,
        lines=_lines(ret),
        refund_cents=ret.refund_cents,
    )


@router.post(
    "/returns",
    response_model=ReturnResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Return items from a delivered Order and record the Refund",
    responses={
        404: {"model": ErrorResponse, "description": "Unknown order ID or email mismatch"},
        422: {
            "model": ErrorResponse,
            "description": "Invalid body, or ORDER_NOT_DELIVERED, RETURN_WINDOW_EXPIRED, "
            "INVALID_QUANTITY, LINE_NOT_ON_ORDER",
        },
    },
)
def create_return(
    body: ReturnRequest,
    conn: Annotated[sqlite3.Connection, Depends(get_connection)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ReturnResponse:
    ret = ReturnService(conn).create_return(
        order_id=body.order_id,
        email=body.email,
        lines={line.line_id: line.quantity for line in body.lines},
        reason=body.reason,
        now=clock.now(),
    )
    return ReturnResponse(
        return_id=ret.return_id,
        order_id=ret.order_id,
        created_at=ret.created_at,
        reason=ret.reason,
        lines=_lines(ret),
        refund_cents=ret.refund_cents,
    )
