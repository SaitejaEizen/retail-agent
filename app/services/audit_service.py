"""Audit use cases: standalone committed entries and reading the trail (FR7, FR8)."""

import sqlite3
from collections.abc import Mapping
from typing import Any, Protocol

from app.domain.audit import AuditAction, AuditEntry, AuditOutcome


class AuditStore(Protocol):
    def record(
        self,
        action: AuditAction,
        order_id: str | None,
        outcome: AuditOutcome,
        details: Mapping[str, Any],
        email: str | None = None,
    ) -> None: ...

    def list(self, order_id: str | None = None) -> tuple[AuditEntry, ...]: ...


class AuditService:
    def __init__(self, conn: sqlite3.Connection, store: AuditStore) -> None:
        self._conn = conn
        self._store = store

    def record_committed(
        self,
        action: AuditAction,
        order_id: str | None,
        outcome: AuditOutcome,
        details: Mapping[str, Any],
        email: str | None = None,
    ) -> None:
        """Write one entry in its own transaction and commit it (lookups, rejections)."""
        with self._conn:
            self._store.record(action, order_id, outcome, details, email)

    def list_entries(self, order_id: str | None = None) -> tuple[AuditEntry, ...]:
        return self._store.list(order_id)
