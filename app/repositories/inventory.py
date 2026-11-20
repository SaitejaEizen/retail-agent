"""Inventory writes. Called only by ReturnService (AD-2) and the seed loader."""

import sqlite3


class InventoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def restock(self, sku: str, quantity: int) -> None:
        """Add returned units to on-hand stock; the caller owns the transaction."""
        cursor = self._conn.execute(
            "UPDATE inventory SET on_hand = on_hand + ? WHERE sku = ?", (quantity, sku)
        )
        if cursor.rowcount != 1:
            raise LookupError(f"No inventory row for SKU {sku}")
