import logging
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_clock
from app.infra.clock import FixedClock

SEED_DAY = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)
FULL_EMAILS = ("asha@example.com", "ben@example.com", "chen@example.com")


def _lookup(client: TestClient, order_id: str, email: str):
    return client.post("/orders/lookup", json={"order_id": order_id, "email": email})


def _mug_line(client: TestClient) -> int:
    lines = _lookup(client, "ORD-1001", "asha@example.com").json()["lines"]
    return next(line["line_id"] for line in lines if line["sku"] == "MUG-001")


def _tick(client: TestClient, seconds: int) -> None:
    clock = FixedClock(SEED_DAY + timedelta(seconds=seconds))
    client.app.dependency_overrides[get_clock] = lambda: clock


def _entries(client: TestClient, **params) -> list[dict]:
    response = client.get("/audit", params=params)
    assert response.status_code == 200
    return response.json()["entries"]


def test_empty_trail(client: TestClient) -> None:
    """FR8: a fresh service has no Audit Entries (seeding is not an audited action)."""
    assert _entries(client) == []


def test_lookup_hit_and_miss_are_audited(client: TestClient) -> None:
    """FR7: found and not-found lookups each write one ORDER_LOOKUP entry."""
    assert _lookup(client, "ORD-1001", "asha@example.com").status_code == 200
    assert _lookup(client, "ORD-1001", "ben@example.com").status_code == 404
    newest, oldest = _entries(client)
    assert (oldest["action"], oldest["outcome"]) == ("ORDER_LOOKUP", "success")
    assert oldest["masked_email"] == "a***@example.com"
    assert (newest["action"], newest["outcome"]) == ("ORDER_LOOKUP", "not_found")
    assert newest["details"] == {"error_code": "ORDER_NOT_FOUND"}
    assert newest["masked_email"] == "b***@example.com"


def test_accepted_return_audit_entries(client: TestClient) -> None:
    """FR7: an accepted Return adds RETURN_REQUESTED, REFUND_CALCULATED and RESTOCK_APPLIED."""
    mug = _mug_line(client)
    response = client.post("/returns", json={
        "order_id": "ORD-1001", "email": "asha@example.com",
        "lines": [{"line_id": mug, "quantity": 1}],
    })
    assert response.status_code == 201
    entries = _entries(client, order_id="ORD-1001")
    assert [(e["action"], e["outcome"]) for e in entries] == [
        ("RESTOCK_APPLIED", "success"),
        ("REFUND_CALCULATED", "success"),
        ("RETURN_REQUESTED", "success"),
        ("ORDER_LOOKUP", "success"),
    ]
    assert entries[1]["details"]["refund_cents"] == 1250
    assert entries[0]["details"]["items"] == [{"sku": "MUG-001", "quantity": 1}]
    assert {e["details"].get("return_id") for e in entries[:3]} == {response.json()["return_id"]}


def test_rejected_return_is_audited_and_changes_nothing_else(
    client: TestClient, db_path: Path
) -> None:
    """FR4 / FR7: a refused return commits one rejected entry; Returns and Inventory unchanged."""
    _tick(client, 0)
    lines = _lookup(client, "ORD-1002", "ben@example.com").json()["lines"]
    conn = sqlite3.connect(db_path)
    stock = conn.execute("SELECT * FROM inventory ORDER BY sku").fetchall()
    response = client.post("/returns", json={
        "order_id": "ORD-1002", "email": "ben@example.com",
        "lines": [{"line_id": lines[0]["line_id"], "quantity": 1}],
    })
    assert response.status_code == 422
    newest = _entries(client, order_id="ORD-1002")[0]
    assert (newest["action"], newest["outcome"]) == ("RETURN_REQUESTED", "rejected")
    assert newest["details"]["error_code"] == "RETURN_WINDOW_EXPIRED"
    assert conn.execute("SELECT COUNT(*) FROM returns").fetchone()[0] == 0
    assert conn.execute("SELECT * FROM inventory ORDER BY sku").fetchall() == stock
    conn.close()


def test_list_newest_first_with_clock_timestamps(client: TestClient) -> None:
    """FR8 / AD-4: entries come newest first, with UTC Z timestamps taken from the Clock."""
    for seconds, (order_id, email) in enumerate(
        [("ORD-1001", "asha@example.com"), ("ORD-1002", "ben@example.com"),
         ("ORD-1003", "chen@example.com")]
    ):
        _tick(client, seconds)
        _lookup(client, order_id, email)
    entries = _entries(client)
    assert [e["order_id"] for e in entries] == ["ORD-1003", "ORD-1002", "ORD-1001"]
    assert [e["created_at"] for e in entries] == [
        "2026-11-19T09:30:02Z", "2026-11-19T09:30:01Z", "2026-11-19T09:30:00Z"
    ]
    assert entries[0]["id"] > entries[1]["id"] > entries[2]["id"]


def test_filter_by_order_id(client: TestClient) -> None:
    """FR8: ?order_id= returns only that Order's entries; an unknown ID returns none."""
    _lookup(client, "ORD-1001", "asha@example.com")
    _lookup(client, "ORD-1002", "ben@example.com")
    _lookup(client, "ORD-1001", "asha@example.com")
    assert [e["order_id"] for e in _entries(client, order_id="ORD-1001")] == ["ORD-1001"] * 2
    assert _entries(client, order_id="ORD-9999") == []
    assert len(_entries(client)) == 3


@pytest.mark.parametrize("order_id", ["", "x" * 65])
def test_bad_filter_is_validation_error(client: TestClient, order_id: str) -> None:
    """FR8 / NFR3: an empty or over-long order_id filter gives 422 VALIDATION_ERROR."""
    response = client.get("/audit", params={"order_id": order_id})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_full_email_never_stored_in_audit_or_logged(
    client: TestClient, db_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """FR7 / AD-5: full emails appear in neither audit_entries nor the logs."""
    caplog.set_level(logging.DEBUG)
    mug = _mug_line(client)
    client.post("/returns", json={
        "order_id": "ORD-1001", "email": "asha@example.com",
        "lines": [{"line_id": mug, "quantity": 1}], "reason": "email me at asha@example.com",
    })
    client.post("/returns", json={
        "order_id": "ORD-1001", "email": "asha@example.com",
        "lines": [{"line_id": mug, "quantity": 9}],
    })
    _lookup(client, "ORD-1002", "ben@example.com")
    _lookup(client, "ORD-1003", "CHEN@example.com")
    conn = sqlite3.connect(db_path)
    audit_text = " ".join(
        str(value) for row in conn.execute("SELECT * FROM audit_entries") for value in row
    ).lower()
    conn.close()
    logs = caplog.text.lower()
    for email in FULL_EMAILS:
        assert email not in audit_text
        assert email not in logs
    assert "a***@example.com" in audit_text
    assert audit_text.count("RETURN_REQUESTED".lower()) == 2


def test_audit_entry_shape(client: TestClient) -> None:
    """FR7 / AD-5: entries have id, created_at, action, outcome, order_id, snake_case details."""
    _lookup(client, "ORD-1001", "asha@example.com")
    (entry,) = _entries(client)
    assert set(entry) == {
        "id", "created_at", "action", "outcome", "order_id", "masked_email", "details"
    }
    assert all(key == key.lower() and " " not in key for key in entry["details"])
