"""ReturnService against a real temporary SQLite file (transaction behaviour needs a DB)."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.infra.clock import FixedClock
from app.infra.db import connect, init_db
from app.repositories.audit import AuditRepository
from app.repositories.inventory import InventoryRepository
from app.repositories.returns import ReturnRepository
from app.services.return_service import ReturnService

SEED_DAY = date(2026, 11, 19)
NOW = datetime(2026, 11, 19, 9, 30, 15, 123456, tzinfo=UTC)


def _service(conn: sqlite3.Connection, **overrides) -> ReturnService:
    return ReturnService(conn, AuditRepository(conn, FixedClock(NOW)), **overrides)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "retail.db"
    init_db(path, SEED_DAY)
    return path


@pytest.fixture
def conn(db: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(db)
    yield connection
    connection.close()


def _line_id(conn: sqlite3.Connection, order_id: str, sku: str) -> int:
    return conn.execute(
        "SELECT line_id FROM order_lines WHERE order_id = ? AND sku = ?", (order_id, sku)
    ).fetchone()[0]


def _on_hand(conn: sqlite3.Connection, sku: str) -> int:
    return conn.execute("SELECT on_hand FROM inventory WHERE sku = ?", (sku,)).fetchone()[0]


def _count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_accepted_return_writes_return_and_restocks(conn: sqlite3.Connection) -> None:
    """FR3 / FR5 / FR6: one Return with its Refund is saved and Inventory is restocked."""
    mug, bag = _line_id(conn, "ORD-1001", "MUG-001"), _line_id(conn, "ORD-1001", "BAG-003")
    mug_before, bag_before = _on_hand(conn, "MUG-001"), _on_hand(conn, "BAG-003")

    ret = _service(conn).create_return(
        "ORD-1001", "asha@example.com", {mug: 2, bag: 1}, "Cracked", NOW
    )

    assert ret.refund_cents == 3399
    assert [(line.line_id, line.quantity, line.refund_cents) for line in ret.lines] == [
        (mug, 2, 2500),
        (bag, 1, 899),
    ]
    assert ret.created_at == datetime(2026, 11, 19, 9, 30, 15, tzinfo=UTC)
    assert not conn.in_transaction
    assert _on_hand(conn, "MUG-001") == mug_before + 2
    assert _on_hand(conn, "BAG-003") == bag_before + 1
    row = conn.execute("SELECT * FROM returns").fetchone()
    assert (row["order_id"], row["reason"], row["refund_cents"]) == ("ORD-1001", "Cracked", 3399)
    assert row["created_at"] == "2026-11-19T09:30:15Z"
    assert ReturnRepository(conn).list_for_order("ORD-1001")[0] == ret


class _FailingInventory:
    def restock(self, sku: str, quantity: int) -> None:
        raise RuntimeError("disk on fire")


def test_failure_after_return_insert_rolls_everything_back(conn: sqlite3.Connection) -> None:
    """NFR1 / FR6: a failure after the Return insert leaves no Return and Inventory unchanged."""
    mug = _line_id(conn, "ORD-1001", "MUG-001")
    before = _on_hand(conn, "MUG-001")
    service = _service(conn, inventory=_FailingInventory())
    with pytest.raises(RuntimeError):
        service.create_return("ORD-1001", "asha@example.com", {mug: 1}, None, NOW)
    assert not conn.in_transaction
    assert _count(conn, "returns") == 0
    assert _count(conn, "return_lines") == 0
    assert _on_hand(conn, "MUG-001") == before


def test_partial_restock_failure_rolls_back_earlier_restock(conn: sqlite3.Connection) -> None:
    """NFR1 / FR6: if the second line's restock fails, the first line's restock is undone."""
    mug, bag = _line_id(conn, "ORD-1001", "MUG-001"), _line_id(conn, "ORD-1001", "BAG-003")
    before = _on_hand(conn, "MUG-001")

    class _FailOnBag(InventoryRepository):
        def restock(self, sku: str, quantity: int) -> None:
            if sku == "BAG-003":
                raise RuntimeError("bag shelf missing")
            super().restock(sku, quantity)

    with pytest.raises(RuntimeError):
        _service(conn, inventory=_FailOnBag(conn)).create_return(
            "ORD-1001", "asha@example.com", {mug: 1, bag: 1}, None, NOW
        )
    assert _on_hand(conn, "MUG-001") == before
    assert _count(conn, "returns") == 0


def test_missing_inventory_row_fails_and_rolls_back(conn: sqlite3.Connection) -> None:
    """NFR1 / FR6: restocking a SKU with no inventory row is an error, not a silent no-op."""
    with pytest.raises(LookupError):
        InventoryRepository(conn).restock("NOPE-000", 1)
    conn.rollback()
    conn.execute("DELETE FROM inventory WHERE sku = 'MUG-001'")
    conn.commit()
    mug = _line_id(conn, "ORD-1001", "MUG-001")
    with pytest.raises(LookupError):
        _service(conn).create_return("ORD-1001", "asha@example.com", {mug: 1}, None, NOW)
    assert _count(conn, "returns") == 0


@pytest.mark.parametrize(
    ("order_id", "email", "lines", "now", "code"),
    [
        ("ORD-9999", "asha@example.com", {1: 1}, NOW, ErrorCode.ORDER_NOT_FOUND),
        ("ORD-1001", "ben@example.com", {1: 1}, NOW, ErrorCode.ORDER_NOT_FOUND),
        ("ORD-1004", "dana@example.com", None, NOW, ErrorCode.ORDER_NOT_DELIVERED),
        ("ORD-1003", "chen@example.com", None, NOW + timedelta(days=1),
         ErrorCode.RETURN_WINDOW_EXPIRED),
        ("ORD-1001", "asha@example.com", {999: 1}, NOW, ErrorCode.LINE_NOT_ON_ORDER),
        ("ORD-1001", "asha@example.com", None, NOW, ErrorCode.INVALID_QUANTITY),
    ],
)
def test_rejections_change_nothing(
    conn: sqlite3.Connection, order_id: str, email: str, lines, now: datetime, code: ErrorCode
) -> None:
    """FR4 / FR6: each rejection raises its code and leaves Returns and Inventory unchanged."""
    if lines is None:
        first_line = conn.execute(
            "SELECT line_id, quantity FROM order_lines WHERE order_id = ? ORDER BY line_id",
            (order_id,),
        ).fetchone()
        qty = first_line["quantity"] + 1 if code is ErrorCode.INVALID_QUANTITY else 1
        lines = {first_line["line_id"]: qty}
    stock = "SELECT sku, on_hand FROM inventory ORDER BY sku"
    stock_before = conn.execute(stock).fetchall()
    with pytest.raises(DomainError) as info:
        _service(conn).create_return(order_id, email, lines, None, now)
    assert info.value.code is code
    assert not conn.in_transaction
    assert _count(conn, "returns") == 0
    assert conn.execute(stock).fetchall() == stock_before


def test_write_lock_serialises_concurrent_returns(db: Path) -> None:
    """FR3 / NFR1: BEGIN IMMEDIATE blocks a second writer, so both can't pass the check."""
    first, second, third = connect(db), sqlite3.connect(db, timeout=0), connect(db)
    try:
        mug = _line_id(first, "ORD-1001", "MUG-001")
        first.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            second.execute("BEGIN IMMEDIATE")
        first.rollback()
        _service(first).create_return("ORD-1001", "asha@example.com", {mug: 2}, None, NOW)
        with pytest.raises(DomainError) as info:
            _service(third).create_return(
                "ORD-1001", "asha@example.com", {mug: 1}, None, NOW
            )
        assert info.value.code is ErrorCode.INVALID_QUANTITY
    finally:
        for connection in (first, second, third):
            connection.close()


def _audit_rows(conn: sqlite3.Connection) -> list[tuple]:
    return [
        (row["action"], row["outcome"], row["order_id"], row["masked_email"],
         json.loads(row["details"]))
        for row in conn.execute("SELECT * FROM audit_entries ORDER BY id")
    ]


def test_accepted_return_writes_three_audit_entries(conn: sqlite3.Connection) -> None:
    """FR7: an accepted Return writes RETURN_REQUESTED, REFUND_CALCULATED and RESTOCK_APPLIED."""
    mug, bag = _line_id(conn, "ORD-1001", "MUG-001"), _line_id(conn, "ORD-1001", "BAG-003")
    ret = _service(conn).create_return(
        "ORD-1001", "asha@example.com", {mug: 2, bag: 1}, "Cracked", NOW
    )
    rid = ret.return_id
    assert _audit_rows(conn) == [
        ("RETURN_REQUESTED", "success", "ORD-1001", "a***@example.com",
         {"return_id": rid, "reason": "Cracked",
          "lines": [{"line_id": mug, "quantity": 2}, {"line_id": bag, "quantity": 1}]}),
        ("REFUND_CALCULATED", "success", "ORD-1001", "a***@example.com",
         {"return_id": rid, "refund_cents": 3399}),
        ("RESTOCK_APPLIED", "success", "ORD-1001", "a***@example.com",
         {"return_id": rid, "items": [{"sku": "MUG-001", "quantity": 2},
                                      {"sku": "BAG-003", "quantity": 1}]}),
    ]


class _AuditFailingOnRestockEntry(AuditRepository):
    def record(self, action, order_id, outcome, details, email=None) -> None:
        super().record(action, order_id, outcome, details, email)
        if action == "RESTOCK_APPLIED":
            raise RuntimeError("audit disk full")


def test_failure_after_audit_writes_rolls_back_entries(conn: sqlite3.Connection) -> None:
    """NFR1 / FR7: a failure after audit writes leaves no Return, stock change or entry."""
    mug = _line_id(conn, "ORD-1001", "MUG-001")
    before = _on_hand(conn, "MUG-001")
    audit = _AuditFailingOnRestockEntry(conn, FixedClock(NOW))
    with pytest.raises(RuntimeError):
        ReturnService(conn, audit).create_return(
            "ORD-1001", "asha@example.com", {mug: 1}, None, NOW
        )
    assert _audit_rows(conn) == []
    assert _count(conn, "returns") == 0
    assert _on_hand(conn, "MUG-001") == before


def test_unexpected_failure_is_not_audited(conn: sqlite3.Connection) -> None:
    """FR7 / NFR1: a non-domain failure rolls back and writes no rejection entry."""
    mug = _line_id(conn, "ORD-1001", "MUG-001")
    with pytest.raises(RuntimeError):
        _service(conn, inventory=_FailingInventory()).create_return(
            "ORD-1001", "asha@example.com", {mug: 1}, None, NOW
        )
    assert _audit_rows(conn) == []


@pytest.mark.parametrize(
    ("order_id", "email", "lines", "code"),
    [
        ("ORD-9999", "asha@example.com", {1: 1}, "ORDER_NOT_FOUND"),
        ("ORD-1001", "ben@example.com", {1: 1}, "ORDER_NOT_FOUND"),
        ("ORD-1004", "dana@example.com", {6: 1}, "ORDER_NOT_DELIVERED"),
        ("ORD-1001", "asha@example.com", {999: 1}, "LINE_NOT_ON_ORDER"),
        ("ORD-1001", "asha@example.com", {1: 5}, "INVALID_QUANTITY"),
    ],
)
def test_rejection_commits_one_rejected_entry(
    conn: sqlite3.Connection, order_id: str, email: str, lines: dict, code: str
) -> None:
    """FR4 / FR7: a refused return commits one RETURN_REQUESTED rejected entry with error_code."""
    with pytest.raises(DomainError):
        _service(conn).create_return(order_id, email, lines, "why", NOW)
    assert not conn.in_transaction
    conn.rollback()  # nothing pending: the entry was already committed
    rows = _audit_rows(conn)
    assert len(rows) == 1
    action, outcome, logged_order, masked, details = rows[0]
    assert (action, outcome, logged_order) == ("RETURN_REQUESTED", "rejected", order_id)
    assert masked == f"{email[0]}***@example.com"
    assert details == {
        "error_code": code,
        "reason": "why",
        "lines": [{"line_id": k, "quantity": v} for k, v in lines.items()],
    }
    assert _count(conn, "returns") == 0
