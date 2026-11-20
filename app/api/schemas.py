"""Pydantic request/response models. The only place Pydantic is used (AD-8)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class LookupRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64, examples=["ORD-1001"])
    email: str = Field(min_length=1, max_length=254, examples=["asha@example.com"])


class OrderLineResponse(BaseModel):
    line_id: int
    sku: str
    quantity: int
    unit_price_cents: int
    returnable_quantity: int


class ReturnSummary(BaseModel):
    return_id: int
    refund_cents: int


class OrderLookupResponse(BaseModel):
    order_id: str
    status: Literal["placed", "shipped", "delivered", "cancelled"]
    delivered_on: date | None
    lines: list[OrderLineResponse]
    total_cents: int
    return_window_ends_on: date | None
    is_returnable: bool
    returns: list[ReturnSummary]
