"""Return use case (FR3–FR6): the only writer of returns, return_lines and inventory (AD-2)."""

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol

from app.domain import rules
from app.domain.audit import AuditAction, AuditOutcome
from app.domain.errors import DomainError, ErrorCode
from app.domain.models import Order, Return, ReturnLine
from app.repositories.inventory import InventoryRepository
from app.repositories.orders import OrderRepository
from app.repositories.returns import ReturnRepository


class OrderReader(Protocol):
    def get(self, order_id: str) -> Order | None: ...


class ReturnStore(Protocol):
    def returned_quantities(self, order_id: str) -> dict[int, int]: ...

    def insert(
        self,
        order_id: str,
        reason: str | None,
        refund_cents: int,
        created_at: datetime,
        lines: Sequence[ReturnLine],
    ) -> int: ...


class InventoryStore(Protocol):
    def restock(self, sku: str, quantity: int) -> None: ...


class AuditWriter(Protocol):
    def record(
        self,
        action: AuditAction,
        order_id: str | None,
        outcome: AuditOutcome,
        details: Mapping[str, Any],
        email: str | None = None,
    ) -> None: ...


class ReturnService:
    def __init__(
        self,
        conn: sqlite3.Connection,
        audit: AuditWriter,
        orders: OrderReader | None = None,
        returns: ReturnStore | None = None,
        inventory: InventoryStore | None = None,
    ) -> None:
        self._conn = conn
        self._audit = audit
        self._orders = orders or OrderRepository(conn)
        self._returns = returns or ReturnRepository(conn)
        self._inventory = inventory or InventoryRepository(conn)

    def create_return(
        self,
        order_id: str,
        email: str,
        lines: Mapping[int, int],
        reason: str | None,
        now: datetime,
    ) -> Return:
        """Validate and record one Return, its Refund, Restock and Audit Entries atomically.

        ``lines`` maps order line ID to quantity. Any error rolls back every write; a
        DomainError rejection is then audited in its own committed transaction (AD-5).
        """
        requested = [{"line_id": line_id, "quantity": qty} for line_id, qty in lines.items()]
        created_at = now.astimezone(UTC).replace(microsecond=0)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            # Re-read inside the write lock so concurrent requests can't both pass the check.
            order = self._orders.get(order_id)
            if order is None or not rules.email_matches(order.customer_email, email):
                raise DomainError(ErrorCode.ORDER_NOT_FOUND)
            returned = self._returns.returned_quantities(order_id)
            rules.check_return_eligibility(order, lines, returned, created_at.date())

            order_lines = {line.line_id: line for line in order.lines}
            return_lines = tuple(
                ReturnLine(
                    line_id=line_id,
                    sku=order_lines[line_id].sku,
                    quantity=quantity,
                    refund_cents=rules.line_refund_cents(order_lines[line_id], quantity),
                )
                for line_id, quantity in lines.items()
            )
            refund = rules.refund_cents(order, lines)
            return_id = self._returns.insert(order_id, reason, refund, created_at, return_lines)
            for line in return_lines:
                self._inventory.restock(line.sku, line.quantity)
            self._audit.record(
                AuditAction.RETURN_REQUESTED,
                order_id,
                AuditOutcome.SUCCESS,
                {"return_id": return_id, "lines": requested, "reason": reason},
                email,
            )
            self._audit.record(
                AuditAction.REFUND_CALCULATED,
                order_id,
                AuditOutcome.SUCCESS,
                {"return_id": return_id, "refund_cents": refund},
                email,
            )
            self._audit.record(
                AuditAction.RESTOCK_APPLIED,
                order_id,
                AuditOutcome.SUCCESS,
                {
                    "return_id": return_id,
                    "items": [
                        {"sku": line.sku, "quantity": line.quantity} for line in return_lines
                    ],
                },
                email,
            )
            self._conn.commit()
        except DomainError as err:
            self._conn.rollback()
            with self._conn:
                self._audit.record(
                    AuditAction.RETURN_REQUESTED,
                    order_id,
                    AuditOutcome.REJECTED,
                    {"error_code": err.code.value, "lines": requested, "reason": reason},
                    email,
                )
            raise
        except BaseException:
            self._conn.rollback()
            raise
        return Return(
            return_id=return_id,
            order_id=order_id,
            reason=reason,
            refund_cents=refund,
            created_at=created_at,
            lines=return_lines,
        )
