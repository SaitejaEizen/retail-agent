from datetime import date

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.domain.models import Order, OrderLine, OrderStatus
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


def test_lookup_returns_order_with_eligibility() -> None:
    """FR1 / FR2: a matching lookup returns lines, total, window end and eligibility."""
    result = OrderService(_Repo()).lookup("ORD-1001", "Asha@Example.com", date(2026, 11, 19))
    assert result.order is ORDER
    assert result.total_cents == 3399
    assert result.return_window_ends_on == date(2026, 12, 7)
    assert result.is_returnable is True
    assert [(v.line.line_id, v.returnable_quantity) for v in result.lines] == [(1, 2), (2, 1)]
    assert result.returns == ()


def test_lookup_after_window_is_not_returnable() -> None:
    """FR2: the same Order looked up on day 31 is no longer returnable."""
    result = OrderService(_Repo()).lookup("ORD-1001", "asha@example.com", date(2026, 12, 8))
    assert result.is_returnable is False
    assert result.return_window_ends_on == date(2026, 12, 7)


@pytest.mark.parametrize(
    ("order_id", "email"), [("ORD-9999", "asha@example.com"), ("ORD-1001", "ben@example.com")]
)
def test_unknown_id_and_wrong_email_are_both_not_found(order_id: str, email: str) -> None:
    """FR1: an unknown ID and a mismatched email raise the same ORDER_NOT_FOUND."""
    with pytest.raises(DomainError) as info:
        OrderService(_Repo()).lookup(order_id, email, date(2026, 11, 19))
    assert info.value.code is ErrorCode.ORDER_NOT_FOUND
    assert info.value.message == "Order not found."
