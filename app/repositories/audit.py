"""The only writer of audit_entries (AD-5)."""

import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.domain.audit import (
    AuditAction,
    AuditEntry,
    AuditOutcome,
    mask_email,
    redact_emails,
)
from app.infra.clock import Clock


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


class AuditRepository:
    def __init__(self, conn: sqlite3.Connection, clock: Clock) -> None:
        self._conn = conn
        self._clock = clock

    def record(
        self,
        action: AuditAction,
        order_id: str | None,
        outcome: AuditOutcome,
        details: Mapping[str, Any],
        email: str | None = None,
    ) -> None:
        """Append one entry. Emails are masked; the caller owns the transaction."""
        self._conn.execute(
            "INSERT INTO audit_entries"
            " (created_at, action, outcome, order_id, masked_email, details)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                _timestamp(self._clock.now()),
                AuditAction(action).value,
                AuditOutcome(outcome).value,
                order_id,
                mask_email(email) if email is not None else None,
                json.dumps(redact_emails(dict(details)), sort_keys=True),
            ),
        )

    def list(self, order_id: str | None = None) -> tuple[AuditEntry, ...]:
        """Entries newest first, optionally for one Order."""
        query = (
            "SELECT id, created_at, action, outcome, order_id, masked_email, details"
            " FROM audit_entries"
        )
        params: tuple[str, ...] = ()
        if order_id is not None:
            query += " WHERE order_id = ?"
            params = (order_id,)
        rows = self._conn.execute(query + " ORDER BY id DESC", params).fetchall()
        return tuple(
            AuditEntry(
                id=row["id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                action=AuditAction(row["action"]),
                outcome=AuditOutcome(row["outcome"]),
                order_id=row["order_id"],
                masked_email=row["masked_email"],
                details=json.loads(row["details"]),
            )
            for row in rows
        )
