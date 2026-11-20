from datetime import date, timedelta

import pytest

from app.domain import rules
from app.domain.errors import DomainError, ErrorCode
from app.domain.models import Order, OrderLine, OrderStatus

DELIVERED_ON = date(2026, 10, 20)


def _order(status: OrderStatus = OrderStatus.DELIVERED, delivered_on: date | None = DELIVERED_ON):
    return Order(
        order_id="ORD-1",
        customer_email="asha@example.com",
        status=status,
        placed_on=date(2026, 10, 15),
        delivered_on=delivered_on,
        lines=(OrderLine(1, "MUG-001", 2, 1250), OrderLine(2, "BAG-003", 1, 899)),
    )


@pytest.mark.parametrize(
    ("days_after", "expected"), [(0, True), (29, True), (30, True), (31, False), (41, False)]
)
def test_window_boundary(days_after: int, expected: bool) -> None:
    """FR2: day 30 after delivery is inside the Return Window, day 31 is not."""
    today = DELIVERED_ON + timedelta(days=days_after)
    assert rules.is_within_return_window(DELIVERED_ON, today) is expected
    assert rules.is_returnable(_order(), today) is expected


def test_window_end_date_for_delivered_order() -> None:
    """FR2: the Return Window ends 30 days after the delivery date."""
    assert rules.return_window_ends_on(_order()) == date(2026, 11, 19)


@pytest.mark.parametrize(
    "status", [OrderStatus.PLACED, OrderStatus.SHIPPED, OrderStatus.CANCELLED]
)
def test_undelivered_orders_have_no_window_and_are_not_returnable(status: OrderStatus) -> None:
    """FR2: Orders that are not delivered have no window end and cannot be returned."""
    order = _order(status=status, delivered_on=None)
    assert rules.return_window_ends_on(order) is None
    assert rules.is_returnable(order, DELIVERED_ON) is False


def test_delivered_status_without_date_is_not_returnable() -> None:
    """FR2: a delivered Order missing its delivery date is treated as not returnable."""
    order = _order(delivered_on=None)
    assert rules.return_window_ends_on(order) is None
    assert rules.is_returnable(order, DELIVERED_ON) is False


def test_returnable_quantity() -> None:
    """FR2: Returnable Quantity is purchased minus already returned, never negative."""
    line = OrderLine(1, "MUG-001", 2, 1250)
    assert rules.returnable_quantity(line) == 2
    assert rules.returnable_quantity(line, 1) == 1
    assert rules.returnable_quantity(line, 5) == 0


def test_fully_returned_order_is_not_returnable() -> None:
    """FR2: inside the window, an Order with nothing left to return is not returnable."""
    assert rules.is_returnable(_order(), DELIVERED_ON, {1: 2, 2: 1}) is False
    assert rules.is_returnable(_order(), DELIVERED_ON, {1: 2}) is True


def test_order_total_is_integer_cents() -> None:
    """FR1: the order total is the sum of unit price × quantity, in integer cents."""
    total = rules.order_total_cents(_order())
    assert total == 3399
    assert isinstance(total, int)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("asha@example.com", True),
        ("ASHA@Example.COM", True),
        ("  asha@example.com ", True),
        ("asha@example.org", False),
        ("", False),
    ],
)
def test_email_matching_ignores_case(given: str, expected: bool) -> None:
    """FR1: email matching ignores letter case and surrounding spaces."""
    assert rules.email_matches("asha@example.com", given) is expected


TODAY = DELIVERED_ON + timedelta(days=12)


def _code(order, requested, returned=None, today=TODAY) -> ErrorCode | None:
    try:
        rules.check_return_eligibility(order, requested, returned or {}, today)
    except DomainError as err:
        return err.code
    return None


def test_eligible_request_passes() -> None:
    """FR3 / FR4: a delivered Order inside the window with valid quantities is eligible."""
    assert _code(_order(), {1: 2, 2: 1}) is None
    assert _code(_order(), {1: 1}, today=DELIVERED_ON + timedelta(days=30)) is None


@pytest.mark.parametrize(
    "status", [OrderStatus.PLACED, OrderStatus.SHIPPED, OrderStatus.CANCELLED]
)
def test_not_delivered_is_rejected(status: OrderStatus) -> None:
    """FR4: Orders that aren't delivered are rejected with ORDER_NOT_DELIVERED."""
    assert _code(_order(status=status, delivered_on=None), {1: 1}) is ErrorCode.ORDER_NOT_DELIVERED


def test_day_31_is_rejected() -> None:
    """FR4: a request on day 31 after delivery is rejected with RETURN_WINDOW_EXPIRED."""
    late = DELIVERED_ON + timedelta(days=31)
    assert _code(_order(), {1: 1}, today=late) is ErrorCode.RETURN_WINDOW_EXPIRED


@pytest.mark.parametrize("quantity", [0, -1, 3])
def test_bad_quantity_is_rejected(quantity: int) -> None:
    """FR4: a quantity ≤ 0 or above the Returnable Quantity is rejected with INVALID_QUANTITY."""
    assert _code(_order(), {1: quantity}) is ErrorCode.INVALID_QUANTITY


def test_quantity_counts_earlier_returns() -> None:
    """FR3 / FR4: 1 of 2 already returned allows 1 more, but not 2."""
    assert _code(_order(), {1: 1}, {1: 1}) is None
    assert _code(_order(), {1: 2}, {1: 1}) is ErrorCode.INVALID_QUANTITY
    assert _code(_order(), {1: 1}, {1: 2}) is ErrorCode.INVALID_QUANTITY


def test_unknown_line_is_rejected() -> None:
    """FR4: a line that isn't on the Order is rejected with LINE_NOT_ON_ORDER."""
    assert _code(_order(), {1: 1, 99: 1}) is ErrorCode.LINE_NOT_ON_ORDER


def test_empty_request_is_rejected() -> None:
    """FR4: a request with no lines is rejected with INVALID_QUANTITY."""
    assert _code(_order(), {}) is ErrorCode.INVALID_QUANTITY


def test_check_order_status_before_window_before_line_before_quantity() -> None:
    """FR4: when several rules fail, the first in the fixed order is reported."""
    late = DELIVERED_ON + timedelta(days=40)
    assert _code(_order(), {99: 0}, today=late) is ErrorCode.RETURN_WINDOW_EXPIRED
    assert _code(_order(), {99: 1, 1: 0}) is ErrorCode.LINE_NOT_ON_ORDER


def test_refund_is_unit_price_times_quantity() -> None:
    """FR5: the Refund is the sum of unit price × quantity returned, in integer cents."""
    order = _order()
    assert rules.refund_cents(order, {1: 1}) == 1250
    assert rules.refund_cents(order, {1: 2, 2: 1}) == 3399
    assert rules.line_refund_cents(order.lines[1], 1) == 899
    assert isinstance(rules.refund_cents(order, {1: 2}), int)
