"""Pydantic request/response models. The only place Pydantic is used (AD-8)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


class ReturnLineResponse(BaseModel):
    line_id: int
    sku: str
    quantity: int
    refund_cents: int


class ReturnSummary(BaseModel):
    return_id: int
    created_at: datetime
    reason: str | None
    lines: list[ReturnLineResponse]
    refund_cents: int


class ReturnResponse(ReturnSummary):
    order_id: str


class ReturnLineRequest(BaseModel):
    line_id: int
    quantity: int  # range is a business rule: <= 0 gives INVALID_QUANTITY, not a schema error


class ReturnRequest(BaseModel):
    order_id: str = Field(min_length=1, max_length=64, examples=["ORD-1001"])
    email: str = Field(min_length=1, max_length=254, examples=["asha@example.com"])
    lines: list[ReturnLineRequest] = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500, examples=["Cracked on arrival"])

    @field_validator("lines")
    @classmethod
    def line_ids_unique(cls, lines: list[ReturnLineRequest]) -> list[ReturnLineRequest]:
        if len({line.line_id for line in lines}) != len(lines):
            raise ValueError("each line_id may appear only once")
        return lines


class OrderLookupResponse(BaseModel):
    order_id: str
    status: Literal["placed", "shipped", "delivered", "cancelled"]
    delivered_on: date | None
    lines: list[OrderLineResponse]
    total_cents: int
    return_window_ends_on: date | None
    is_returnable: bool
    returns: list[ReturnSummary]
