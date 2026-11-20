"""Pure business rules (AD-1). Every input, including ``today``, is an argument (AD-4)."""

from collections.abc import Mapping
from datetime import date, timedelta

from app.domain.errors import DomainError, ErrorCode
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


def check_return_eligibility(
    order: Order,
    requested: Mapping[int, int],
    returned_by_line: Mapping[int, int],
    today: date,
) -> None:
    """Raise the first DomainError that makes this return request ineligible (FR4).

    Checks run in a fixed order: delivered, inside the window, every line on the
    Order, then every quantity between 1 and the line's Returnable Quantity.
    """
    if order.status is not OrderStatus.DELIVERED or order.delivered_on is None:
        raise DomainError(ErrorCode.ORDER_NOT_DELIVERED)
    if not is_within_return_window(order.delivered_on, today):
        raise DomainError(ErrorCode.RETURN_WINDOW_EXPIRED)
    lines = {line.line_id: line for line in order.lines}
    if any(line_id not in lines for line_id in requested):
        raise DomainError(ErrorCode.LINE_NOT_ON_ORDER)
    if not requested:
        raise DomainError(ErrorCode.INVALID_QUANTITY)
    for line_id, quantity in requested.items():
        available = returnable_quantity(lines[line_id], returned_by_line.get(line_id, 0))
        if quantity <= 0 or quantity > available:
            raise DomainError(ErrorCode.INVALID_QUANTITY)


def line_refund_cents(line: OrderLine, quantity: int) -> int:
    """Unit price paid × quantity returned, in integer cents (FR5)."""
    return line.unit_price_cents * quantity


def refund_cents(order: Order, requested: Mapping[int, int]) -> int:
    """The Return's Refund: the sum of each returned line's refund (FR5)."""
    lines = {line.line_id: line for line in order.lines}
    return sum(line_refund_cents(lines[line_id], qty) for line_id, qty in requested.items())
