"""Pure business rules (AD-1). Every input, including ``today``, is an argument (AD-4)."""

from collections.abc import Mapping
from datetime import date, timedelta

from app.domain.models import Order, OrderLine, OrderStatus

RETURN_WINDOW_DAYS = 30


def email_matches(stored: str, given: str) -> bool:
    """Emails match ignoring letter case and surrounding whitespace."""
    return stored.strip().casefold() == given.strip().casefold()


def order_total_cents(order: Order) -> int:
    return sum(line.unit_price_cents * line.quantity for line in order.lines)


def return_window_ends_on(order: Order) -> date | None:
    """Last day (inclusive) a delivered Order can be returned; None if not delivered."""
    if order.status is not OrderStatus.DELIVERED or order.delivered_on is None:
        return None
    return order.delivered_on + timedelta(days=RETURN_WINDOW_DAYS)


def is_within_return_window(delivered_on: date, today: date) -> bool:
    """Day 30 after delivery is still inside the window; day 31 is not."""
    return today <= delivered_on + timedelta(days=RETURN_WINDOW_DAYS)


def returnable_quantity(line: OrderLine, already_returned: int = 0) -> int:
    """Quantity purchased minus quantity already returned, never below zero."""
    return max(line.quantity - already_returned, 0)


def is_returnable(
    order: Order, today: date, returned_by_line: Mapping[int, int] | None = None
) -> bool:
    """Delivered, inside the window, and at least one unit still returnable."""
    if order.status is not OrderStatus.DELIVERED or order.delivered_on is None:
        return False
    if not is_within_return_window(order.delivered_on, today):
        return False
    returned = returned_by_line or {}
    return any(returnable_quantity(line, returned.get(line.line_id, 0)) > 0 for line in order.lines)
