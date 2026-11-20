from datetime import UTC, date, datetime

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.domain.models import Order, OrderLine, OrderStatus, Return, ReturnLine
from app.services.order_service import OrderService

ORDER = Order(
    order_id="ORD-1001",
    customer_email="asha@example.com",
    status=OrderStatus.DELIVERED,
    placed_on=date(2026, 11, 4),
    delivered_on=date(2026, 11, 7),
    lines=(OrderLine(1, "MUG-001", 2, 1250), OrderLine(2, "BAG-003", 1, 899)),
)


class _Repo:
    def get(self, order_id: str) -> Order | None:
        return ORDER if order_id == ORDER.order_id else None


class _Returns:
    def __init__(self, returns: tuple[Return, ...] = ()) -> None:
        self._returns = returns

    def returned_quantities(self, order_id: str) -> dict[int, int]:
        totals: dict[int, int] = {}
        for ret in self._returns:
            for line in ret.lines:
                totals[line.line_id] = totals.get(line.line_id, 0) + line.quantity
        return totals

    def list_for_order(self, order_id: str) -> tuple[Return, ...]:
        return self._returns


def _service(returns: tuple[Return, ...] = ()) -> OrderService:
    return OrderService(_Repo(), _Returns(returns))


def test_lookup_returns_order_with_eligibility() -> None:
    """FR1 / FR2: a matching lookup returns lines, total, window end and eligibility."""
    result = _service().lookup("ORD-1001", "Asha@Example.com", date(2026, 11, 19))
    assert result.order is ORDER
    assert result.total_cents == 3399
    assert result.return_window_ends_on == date(2026, 12, 7)
    assert result.is_returnable is True
    assert [(v.line.line_id, v.returnable_quantity) for v in result.lines] == [(1, 2), (2, 1)]
    assert result.returns == ()


def test_lookup_after_window_is_not_returnable() -> None:
    """FR2: the same Order looked up on day 31 is no longer returnable."""
    result = _service().lookup("ORD-1001", "asha@example.com", date(2026, 12, 8))
    assert result.is_returnable is False
    assert result.return_window_ends_on == date(2026, 12, 7)


@pytest.mark.parametrize(
    ("order_id", "email"), [("ORD-9999", "asha@example.com"), ("ORD-1001", "ben@example.com")]
)
def test_unknown_id_and_wrong_email_are_both_not_found(order_id: str, email: str) -> None:
    """FR1: an unknown ID and a mismatched email raise the same ORDER_NOT_FOUND."""
    with pytest.raises(DomainError) as info:
        _service().lookup(order_id, email, date(2026, 11, 19))
    assert info.value.code is ErrorCode.ORDER_NOT_FOUND
    assert info.value.message == "Order not found."


def _return(return_id: int, line_id: int, sku: str, quantity: int, cents: int) -> Return:
    return Return(
        return_id=return_id,
        order_id="ORD-1001",
        reason=None,
        refund_cents=cents * quantity,
        created_at=datetime(2026, 11, 10, tzinfo=UTC),
        lines=(ReturnLine(line_id, sku, quantity, cents * quantity),),
    )


def test_lookup_reflects_existing_returns() -> None:
    """FR2: lookup lists Returns and reduces Returnable Quantity by units already returned."""
    existing = (_return(1, 1, "MUG-001", 1, 1250),)
    result = _service(existing).lookup("ORD-1001", "asha@example.com", date(2026, 11, 19))
    assert result.returns == existing
    assert [(v.line.line_id, v.returnable_quantity) for v in result.lines] == [(1, 1), (2, 1)]
    assert result.is_returnable is True


def test_fully_returned_order_is_not_returnable_on_lookup() -> None:
    """FR2: once every unit is returned, lookup reports is_returnable false inside the window."""
    existing = (_return(1, 1, "MUG-001", 2, 1250), _return(2, 2, "BAG-003", 1, 899))
    result = _service(existing).lookup("ORD-1001", "asha@example.com", date(2026, 11, 19))
    assert [v.returnable_quantity for v in result.lines] == [0, 0]
    assert result.is_returnable is False
