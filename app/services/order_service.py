"""Order lookup use case (FR1, FR2)."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from app.domain import rules
from app.domain.audit import AuditAction, AuditOutcome
from app.domain.errors import DomainError, ErrorCode
from app.domain.models import Order, OrderLine, Return


class OrderReader(Protocol):
    def get(self, order_id: str) -> Order | None: ...


class ReturnReader(Protocol):
    def returned_quantities(self, order_id: str) -> dict[int, int]: ...

    def list_for_order(self, order_id: str) -> tuple[Return, ...]: ...


class CommittedAudit(Protocol):
    def record_committed(
        self,
        action: AuditAction,
        order_id: str | None,
        outcome: AuditOutcome,
        details: Mapping[str, Any],
        email: str | None = None,
    ) -> None: ...


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
    returns: tuple[Return, ...]


class OrderService:
    def __init__(self, orders: OrderReader, returns: ReturnReader, audit: CommittedAudit) -> None:
        self._orders = orders
        self._returns = returns
        self._audit = audit

    def lookup(self, order_id: str, email: str, today: date) -> OrderLookup:
        """Return the Order with eligibility, or ORDER_NOT_FOUND for unknown ID or wrong email.

        Either way one ORDER_LOOKUP Audit Entry is committed (FR7).
        """
        order = self._orders.get(order_id)
        if order is None or not rules.email_matches(order.customer_email, email):
            self._audit.record_committed(
                AuditAction.ORDER_LOOKUP,
                order_id,
                AuditOutcome.NOT_FOUND,
                {"error_code": ErrorCode.ORDER_NOT_FOUND.value},
                email,
            )
            raise DomainError(ErrorCode.ORDER_NOT_FOUND)
        returned = self._returns.returned_quantities(order.order_id)
        result = OrderLookup(
            order=order,
            lines=tuple(
                LineView(
                    line=line,
                    returnable_quantity=rules.returnable_quantity(
                        line, returned.get(line.line_id, 0)
                    ),
                )
                for line in order.lines
            ),
            total_cents=rules.order_total_cents(order),
            return_window_ends_on=rules.return_window_ends_on(order),
            is_returnable=rules.is_returnable(order, today, returned),
            returns=self._returns.list_for_order(order.order_id),
        )
        self._audit.record_committed(
            AuditAction.ORDER_LOOKUP,
            order.order_id,
            AuditOutcome.SUCCESS,
            {"status": order.status.value, "is_returnable": result.is_returnable},
            email,
        )
        return result
