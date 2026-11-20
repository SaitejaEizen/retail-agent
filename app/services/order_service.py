"""Order lookup use case (FR1, FR2)."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.domain import rules
from app.domain.errors import DomainError, ErrorCode
from app.domain.models import Order, OrderLine


class OrderReader(Protocol):
    def get(self, order_id: str) -> Order | None: ...


@dataclass(frozen=True)
class LineView:
    line: OrderLine
    returnable_quantity: int


@dataclass(frozen=True)
class OrderLookup:
    order: Order
    lines: tuple[LineView, ...]
    total_cents: int
    return_window_ends_on: date | None
    is_returnable: bool
    returns: tuple[()] = ()  # story 2.1 fills this in from real Returns


class OrderService:
    def __init__(self, orders: OrderReader) -> None:
        self._orders = orders

    def lookup(self, order_id: str, email: str, today: date) -> OrderLookup:
        """Return the Order with eligibility, or ORDER_NOT_FOUND for unknown ID or wrong email."""
        order = self._orders.get(order_id)
        if order is None or not rules.email_matches(order.customer_email, email):
            raise DomainError(ErrorCode.ORDER_NOT_FOUND)
        return OrderLookup(
            order=order,
            lines=tuple(
                LineView(line=line, returnable_quantity=rules.returnable_quantity(line))
                for line in order.lines
            ),
            total_cents=rules.order_total_cents(order),
            return_window_ends_on=rules.return_window_ends_on(order),
            is_returnable=rules.is_returnable(order, today),
        )
