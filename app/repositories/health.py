"""Database reachability probe."""

import sqlite3


class HealthRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def ping(self) -> None:
        """Run a real query against the schema; raises sqlite3.Error if it fails."""
        self._conn.execute("SELECT 1 FROM orders LIMIT 1").fetchall()
