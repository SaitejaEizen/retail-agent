"""POST /orders/lookup (FR1, FR2). Email travels only in the body (AD-9)."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_clock, get_connection
from app.api.schemas import (
    ErrorResponse,
    LookupRequest,
    OrderLineResponse,
    OrderLookupResponse,
)
from app.infra.clock import Clock
from app.repositories.orders import OrderRepository
from app.services.order_service import OrderService

router = APIRouter(tags=["orders"])


@router.post(
    "/orders/lookup",
    response_model=OrderLookupResponse,
    summary="Look up an Order and its return eligibility",
    responses={
        404: {"model": ErrorResponse, "description": "Unknown order ID or email mismatch"},
        422: {"model": ErrorResponse, "description": "Invalid request body"},
    },
)
def lookup_order(
    body: LookupRequest,
    conn: Annotated[sqlite3.Connection, Depends(get_connection)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> OrderLookupResponse:
    result = OrderService(OrderRepository(conn)).lookup(body.order_id, body.email, clock.today())
    order = result.order
    return OrderLookupResponse(
        order_id=order.order_id,
        status=order.status.value,
        delivered_on=order.delivered_on,
        lines=[
            OrderLineResponse(
                line_id=view.line.line_id,
                sku=view.line.sku,
                quantity=view.line.quantity,
                unit_price_cents=view.line.unit_price_cents,
                returnable_quantity=view.returnable_quantity,
            )
            for view in result.lines
        ],
        total_cents=result.total_cents,
        return_window_ends_on=result.return_window_ends_on,
        is_returnable=result.is_returnable,
        returns=[],
    )
