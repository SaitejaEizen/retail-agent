"""Reads and writes Returns. Writes are called only by ReturnService (AD-2)."""

import sqlite3
from collections.abc import Sequence
from datetime import datetime

from app.domain.models import Return, ReturnLine


def _format_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class ReturnRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def returned_quantities(self, order_id: str) -> dict[int, int]:
        """Units already returned per order line."""
        rows = self._conn.execute(
            "SELECT rl.line_id, SUM(rl.quantity) AS returned"
            " FROM return_lines rl JOIN returns r ON r.return_id = rl.return_id"
            " WHERE r.order_id = ? GROUP BY rl.line_id",
            (order_id,),
        ).fetchall()
        return {row["line_id"]: row["returned"] for row in rows}

    def list_for_order(self, order_id: str) -> tuple[Return, ...]:
        """All Returns on an Order, oldest first, with their lines."""
        returns = self._conn.execute(
            "SELECT return_id, order_id, reason, refund_cents, created_at"
            " FROM returns WHERE order_id = ? ORDER BY return_id",
            (order_id,),
        ).fetchall()
        lines = self._conn.execute(
            "SELECT rl.return_id, rl.line_id, ol.sku, rl.quantity, rl.refund_cents"
            " FROM return_lines rl"
            " JOIN returns r ON r.return_id = rl.return_id"
            " JOIN order_lines ol ON ol.line_id = rl.line_id"
            " WHERE r.order_id = ? ORDER BY rl.return_line_id",
            (order_id,),
        ).fetchall()
        lines_by_return: dict[int, list[ReturnLine]] = {}
        for line in lines:
            lines_by_return.setdefault(line["return_id"], []).append(
                ReturnLine(line["line_id"], line["sku"], line["quantity"], line["refund_cents"])
            )
        return tuple(
            Return(
                return_id=row["return_id"],
                order_id=row["order_id"],
                reason=row["reason"],
                refund_cents=row["refund_cents"],
                created_at=datetime.fromisoformat(row["created_at"]),
                lines=tuple(lines_by_return.get(row["return_id"], ())),
            )
            for row in returns
        )

    def insert(
        self,
        order_id: str,
        reason: str | None,
        refund_cents: int,
        created_at: datetime,
        lines: Sequence[ReturnLine],
    ) -> int:
        """Insert a Return and its lines; the caller owns the transaction."""
        cursor = self._conn.execute(
            "INSERT INTO returns (order_id, reason, refund_cents, created_at)"
            " VALUES (?, ?, ?, ?)",
            (order_id, reason, refund_cents, _format_timestamp(created_at)),
        )
        return_id = cursor.lastrowid
        assert return_id is not None
        self._conn.executemany(
            "INSERT INTO return_lines (return_id, line_id, quantity, refund_cents)"
            " VALUES (?, ?, ?, ?)",
            [(return_id, line.line_id, line.quantity, line.refund_cents) for line in lines],
        )
        return return_id
