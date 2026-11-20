import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.domain.audit import AuditAction, AuditOutcome
from app.infra.clock import FixedClock
from app.infra.db import connect, init_db
from app.repositories.audit import AuditRepository
from app.services.audit_service import AuditService

NOW = datetime(2026, 11, 19, 9, 30, 15, 999, tzinfo=UTC)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    path = tmp_path / "retail.db"
    init_db(path, date(2026, 11, 19))
    connection = connect(path)
    yield connection
    connection.close()


def _rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM audit_entries ORDER BY id").fetchall()


def test_record_masks_email_and_uses_clock(conn: sqlite3.Connection) -> None:
    """FR7 / AD-5: record stores a masked email, a Clock-based UTC Z timestamp and JSON details."""
    repo = AuditRepository(conn, FixedClock(NOW))
    repo.record(
        AuditAction.ORDER_LOOKUP, "ORD-1001", AuditOutcome.SUCCESS,
        {"is_returnable": True, "note": "from asha@example.com"}, "Asha@Example.com",
    )
    conn.commit()
    (row,) = _rows(conn)
    assert row["created_at"] == "2026-11-19T09:30:15Z"
    assert (row["action"], row["outcome"], row["order_id"]) == (
        "ORDER_LOOKUP", "success", "ORD-1001"
    )
    assert row["masked_email"] == "a***@example.com"
    assert json.loads(row["details"]) == {"is_returnable": True, "note": "from a***@example.com"}
    assert "asha@example.com" not in " ".join(str(value) for value in tuple(row)).lower()


def test_record_without_email_or_order(conn: sqlite3.Connection) -> None:
    """FR7: an entry can be recorded without an email or Order ID."""
    AuditRepository(conn, FixedClock(NOW)).record(
        AuditAction.RETURN_REQUESTED, None, AuditOutcome.REJECTED, {"error_code": "X"}
    )
    (row,) = _rows(conn)
    assert row["masked_email"] is None
    assert row["order_id"] is None


def test_record_rejects_unknown_action(conn: sqlite3.Connection) -> None:
    """FR7 / AD-5: only the fixed set of actions can be recorded."""
    with pytest.raises(ValueError):
        AuditRepository(conn, FixedClock(NOW)).record(
            "SOMETHING_ELSE", "ORD-1001", AuditOutcome.SUCCESS, {}  # type: ignore[arg-type]
        )


def test_update_and_delete_are_blocked(conn: sqlite3.Connection) -> None:
    """FR7 / AD-5: triggers abort any UPDATE or DELETE on audit_entries."""
    AuditRepository(conn, FixedClock(NOW)).record(
        AuditAction.ORDER_LOOKUP, "ORD-1001", AuditOutcome.SUCCESS, {}
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE audit_entries SET outcome = 'rejected'")
    conn.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM audit_entries")
    conn.rollback()
    assert len(_rows(conn)) == 1
    assert _rows(conn)[0]["outcome"] == "success"


def test_list_newest_first_and_filtered(conn: sqlite3.Connection) -> None:
    """FR8: entries are listed newest first, optionally filtered by Order ID."""
    for offset, order_id in enumerate(["ORD-1001", "ORD-1002", "ORD-1001"]):
        AuditRepository(conn, FixedClock(NOW + timedelta(seconds=offset))).record(
            AuditAction.ORDER_LOOKUP, order_id, AuditOutcome.SUCCESS, {"n": offset}
        )
    conn.commit()
    repo = AuditRepository(conn, FixedClock(NOW))
    assert [entry.details["n"] for entry in repo.list()] == [2, 1, 0]
    only = repo.list("ORD-1001")
    assert [entry.details["n"] for entry in only] == [2, 0]
    assert only[0].created_at == datetime(2026, 11, 19, 9, 30, 17, tzinfo=UTC)
    assert only[0].action is AuditAction.ORDER_LOOKUP
    assert only[0].outcome is AuditOutcome.SUCCESS
    assert repo.list("ORD-9999") == ()


def test_record_committed_commits_own_transaction(conn: sqlite3.Connection) -> None:
    """FR7 / AD-5: a standalone entry is committed even though nothing else is."""
    service = AuditService(conn, AuditRepository(conn, FixedClock(NOW)))
    service.record_committed(
        AuditAction.ORDER_LOOKUP, "ORD-9999", AuditOutcome.NOT_FOUND,
        {"error_code": "ORDER_NOT_FOUND"}, "x@example.com",
    )
    assert not conn.in_transaction
    conn.rollback()
    assert [entry.outcome for entry in service.list_entries()] == [AuditOutcome.NOT_FOUND]


def test_existing_db_gains_audit_table_and_triggers(tmp_path: Path) -> None:
    """FR7 / AD-7: a database created before story 2.2 gets the table and triggers on restart."""
    path = tmp_path / "old.db"
    init_db(path, date(2026, 11, 19))
    raw = sqlite3.connect(path)
    raw.executescript(
        "DROP TRIGGER audit_entries_no_update; DROP TRIGGER audit_entries_no_delete;"
        " DROP TABLE audit_entries;"
    )
    raw.close()
    init_db(path, date(2026, 11, 19))
    raw = sqlite3.connect(path)
    try:
        triggers = {
            name for (name,) in raw.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
    finally:
        raw.close()
    assert triggers == {"audit_entries_no_update", "audit_entries_no_delete"}
