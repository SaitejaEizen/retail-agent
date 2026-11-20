import sqlite3
from datetime import date, timedelta
from pathlib import Path

from app.infra.db import connect, init_db
from app.infra.seed import ORDERS

REF = date(2026, 11, 19)


def _orders(db: Path) -> list[sqlite3.Row]:
    conn = connect(db)
    try:
        return conn.execute("SELECT * FROM orders ORDER BY order_id").fetchall()
    finally:
        conn.close()


def test_schema_creates_only_story_tables(tmp_path: Path) -> None:
    """FR3 / FR10 / AD-7: schema.sql creates the catalogue, order and return tables only."""
    db = tmp_path / "retail.db"
    init_db(db, REF)
    conn = connect(db)
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    finally:
        conn.close()
    assert tables == {"products", "inventory", "orders", "order_lines", "returns", "return_lines"}


def test_seed_covers_every_status_and_window_case(tmp_path: Path) -> None:
    """FR10: seed has every Order Status, and delivered Orders inside, past and on day 30."""
    db = tmp_path / "retail.db"
    init_db(db, REF)
    rows = _orders(db)
    assert {r["status"] for r in rows} == {"placed", "shipped", "delivered", "cancelled"}
    ages = {
        (REF - date.fromisoformat(r["delivered_on"])).days
        for r in rows
        if r["status"] == "delivered"
    }
    assert 30 in ages
    assert any(age < 30 for age in ages)
    assert any(age > 30 for age in ages)
    day_30 = (REF - timedelta(days=30)).isoformat()
    assert {r["order_id"] for r in rows if r["delivered_on"] == day_30} == {"ORD-1003"}


def test_seed_lines_inventory_and_money_are_integers(tmp_path: Path) -> None:
    """FR10 / AD-3: every Order has lines, prices are integer cents, every product is stocked."""
    db = tmp_path / "retail.db"
    init_db(db, REF)
    conn = connect(db)
    try:
        lines = conn.execute("SELECT * FROM order_lines").fetchall()
        orders_without_lines = conn.execute(
            "SELECT COUNT(*) FROM orders o WHERE NOT EXISTS"
            " (SELECT 1 FROM order_lines l WHERE l.order_id = o.order_id)"
        ).fetchone()[0]
        unstocked = conn.execute(
            "SELECT COUNT(*) FROM products p LEFT JOIN inventory i USING (sku) WHERE i.sku IS NULL"
        ).fetchone()[0]
    finally:
        conn.close()
    assert len(lines) == sum(len(order[5]) for order in ORDERS)
    assert all(isinstance(line["unit_price_cents"], int) for line in lines)
    assert orders_without_lines == 0
    assert unstocked == 0


def test_restart_does_not_duplicate_seed(tmp_path: Path) -> None:
    """FR10: running startup twice leaves exactly one copy of the seed set."""
    db = tmp_path / "retail.db"
    init_db(db, REF)
    init_db(db, REF + timedelta(days=5))
    rows = _orders(db)
    assert len(rows) == len(ORDERS)
    conn = connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM order_lines").fetchone()[0] == sum(
            len(order[5]) for order in ORDERS
        )
        assert conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 4
    finally:
        conn.close()
    # Dates come from the first seed, not the second start.
    assert next(r for r in rows if r["order_id"] == "ORD-1003")["delivered_on"] == "2026-10-20"


def test_connect_without_create_refuses_missing_file(tmp_path: Path) -> None:
    """FR9 / AD-7: request connections never silently create an empty database."""
    try:
        connect(tmp_path / "missing.db")
    except sqlite3.OperationalError:
        pass
    else:  # pragma: no cover - the assertion is the point
        raise AssertionError("connect() created a missing database")
    assert not (tmp_path / "missing.db").exists()
