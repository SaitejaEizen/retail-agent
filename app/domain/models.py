"""Domain entities (AD-8): frozen dataclasses, no framework or database types."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class OrderStatus(StrEnum):
    PLACED = "placed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class OrderLine:
    line_id: int
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class Order:
    order_id: str
    customer_email: str
    status: OrderStatus
    placed_on: date
    delivered_on: date | None
    lines: tuple[OrderLine, ...]


@dataclass(frozen=True)
class ReturnLine:
    line_id: int
    sku: str
    quantity: int
    refund_cents: int


@dataclass(frozen=True)
class Return:
    return_id: int
    order_id: str
    reason: str | None
    refund_cents: int
    created_at: datetime
    lines: tuple[ReturnLine, ...]
