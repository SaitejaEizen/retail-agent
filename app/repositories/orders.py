"""Reads Orders and their lines from SQLite."""

import sqlite3
from datetime import date

from app.domain.models import Order, OrderLine, OrderStatus


class OrderRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, order_id: str) -> Order | None:
        row = self._conn.execute(
            "SELECT order_id, customer_email, status, placed_on, delivered_on"
            " FROM orders WHERE order_id = ?",
            (order_id,),
        ).fetchone()
        if row is None:
            return None
        lines = self._conn.execute(
            "SELECT line_id, sku, quantity, unit_price_cents"
            " FROM order_lines WHERE order_id = ? ORDER BY line_id",
            (order_id,),
        ).fetchall()
        return Order(
            order_id=row["order_id"],
            customer_email=row["customer_email"],
            status=OrderStatus(row["status"]),
            placed_on=date.fromisoformat(row["placed_on"]),
            delivered_on=(
                date.fromisoformat(row["delivered_on"]) if row["delivered_on"] else None
            ),
            lines=tuple(
                OrderLine(
                    line_id=line["line_id"],
                    sku=line["sku"],
                    quantity=line["quantity"],
                    unit_price_cents=line["unit_price_cents"],
                )
                for line in lines
            ),
        )
