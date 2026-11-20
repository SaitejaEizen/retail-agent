import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_clock
from app.infra.clock import FixedClock

SEED_DAY = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


def _lines(client: TestClient, order_id: str, email: str) -> dict[str, dict]:
    body = client.post("/orders/lookup", json={"order_id": order_id, "email": email}).json()
    return {line["sku"]: line for line in body["lines"]}


def _return(client: TestClient, order_id: str, email: str, lines: list[dict], **extra):
    payload = {"order_id": order_id, "email": email, "lines": lines, **extra}
    return client.post("/returns", json=payload)


def _db_state(db_path: Path) -> tuple[int, list[tuple]]:
    conn = sqlite3.connect(db_path)
    try:
        returns = conn.execute("SELECT COUNT(*) FROM returns").fetchone()[0]
        stock = conn.execute("SELECT sku, on_hand FROM inventory ORDER BY sku").fetchall()
    finally:
        conn.close()
    return returns, stock


def _on_hand(db_path: Path, sku: str) -> int:
    return dict(_db_state(db_path)[1])[sku]


def test_accept_single_line(client: TestClient, db_path: Path) -> None:
    """FR3 / FR5 / FR6: a valid return gives 201 with the Return and its Refund, and restocks."""
    mug = _lines(client, "ORD-1001", "asha@example.com")["MUG-001"]
    before = _on_hand(db_path, "MUG-001")
    response = _return(
        client, "ORD-1001", "asha@example.com",
        [{"line_id": mug["line_id"], "quantity": 1}], reason="Cracked mug",
    )
    assert response.status_code == 201
    body = response.json()
    assert body == {
        "return_id": body["return_id"],
        "order_id": "ORD-1001",
        "created_at": "2026-11-19T09:30:00Z",
        "reason": "Cracked mug",
        "lines": [
            {"line_id": mug["line_id"], "sku": "MUG-001", "quantity": 1, "refund_cents": 1250}
        ],
        "refund_cents": 1250,
    }
    assert isinstance(body["return_id"], int)
    assert _on_hand(db_path, "MUG-001") == before + 1


def test_accept_multi_line_refund_sum(client: TestClient, db_path: Path) -> None:
    """FR5 / FR6: the Refund is the sum of unit price × quantity, and every SKU is restocked."""
    lines = _lines(client, "ORD-1001", "asha@example.com")
    _, stock_before = _db_state(db_path)
    response = _return(client, "ORD-1001", "ASHA@example.com", [
        {"line_id": lines["MUG-001"]["line_id"], "quantity": 2},
        {"line_id": lines["BAG-003"]["line_id"], "quantity": 1},
    ])
    assert response.status_code == 201
    assert response.json()["refund_cents"] == 3399
    assert response.json()["reason"] is None
    before, after = dict(stock_before), dict(_db_state(db_path)[1])
    assert after["MUG-001"] == before["MUG-001"] + 2
    assert after["BAG-003"] == before["BAG-003"] + 1
    assert after["TEE-002"] == before["TEE-002"]


def test_partial_returns_up_to_returnable_quantity(client: TestClient, db_path: Path) -> None:
    """FR3 / FR4: on a 2-unit line, two 1-unit returns succeed and a third is INVALID_QUANTITY."""
    mug_id = _lines(client, "ORD-1001", "asha@example.com")["MUG-001"]["line_id"]
    line = [{"line_id": mug_id, "quantity": 1}]
    assert _return(client, "ORD-1001", "asha@example.com", line).status_code == 201
    assert _return(client, "ORD-1001", "asha@example.com", line).status_code == 201
    state = _db_state(db_path)
    third = _return(client, "ORD-1001", "asha@example.com", line)
    assert third.status_code == 422
    assert third.json()["error"]["code"] == "INVALID_QUANTITY"
    assert _db_state(db_path) == state


@pytest.mark.parametrize(("days_after_seed", "status"), [(0, 201), (1, 422)])
def test_day_30_accepted_day_31_rejected(
    client: TestClient, db_path: Path, days_after_seed: int, status: int
) -> None:
    """FR4: ORD-1003 (delivered 30 days before seed day) can be returned on day 30, not day 31."""
    lamp_id = _lines(client, "ORD-1003", "chen@example.com")["LMP-004"]["line_id"]
    clock = FixedClock(SEED_DAY + timedelta(days=days_after_seed))
    client.app.dependency_overrides[get_clock] = lambda: clock
    state = _db_state(db_path)
    lamp = [{"line_id": lamp_id, "quantity": 1}]
    response = _return(client, "ORD-1003", "chen@example.com", lamp)
    assert response.status_code == status
    if status == 422:
        assert response.json()["error"]["code"] == "RETURN_WINDOW_EXPIRED"
        assert _db_state(db_path) == state


@pytest.mark.parametrize(
    ("order_id", "email"),
    [("ORD-1004", "dana@example.com"), ("ORD-1005", "eli@example.com"),
     ("ORD-1006", "fatima@example.com")],
)
def test_not_delivered_rejected(
    client: TestClient, db_path: Path, order_id: str, email: str
) -> None:
    """FR4: placed, shipped and cancelled Orders are rejected with ORDER_NOT_DELIVERED."""
    line = next(iter(_lines(client, order_id, email).values()))
    state = _db_state(db_path)
    response = _return(client, order_id, email, [{"line_id": line["line_id"], "quantity": 1}])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ORDER_NOT_DELIVERED"
    assert _db_state(db_path) == state


@pytest.mark.parametrize("quantity", [0, -1, 3])
def test_bad_quantity_rejected(client: TestClient, db_path: Path, quantity: int) -> None:
    """FR4: quantity ≤ 0 or more than the Returnable Quantity gives 422 INVALID_QUANTITY."""
    mug_id = _lines(client, "ORD-1001", "asha@example.com")["MUG-001"]["line_id"]
    state = _db_state(db_path)
    response = _return(
        client, "ORD-1001", "asha@example.com", [{"line_id": mug_id, "quantity": quantity}]
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_QUANTITY"
    assert _db_state(db_path) == state


def test_line_from_another_order_rejected(client: TestClient, db_path: Path) -> None:
    """FR4: a line_id that belongs to a different Order gives 422 LINE_NOT_ON_ORDER."""
    tee_id = _lines(client, "ORD-1002", "ben@example.com")["TEE-002"]["line_id"]
    state = _db_state(db_path)
    response = _return(
        client, "ORD-1001", "asha@example.com", [{"line_id": tee_id, "quantity": 1}]
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LINE_NOT_ON_ORDER"
    assert _db_state(db_path) == state


def test_unknown_order_and_wrong_email_identical_404(client: TestClient, db_path: Path) -> None:
    """FR4 / FR1: unknown order and wrong email both give the same 404 ORDER_NOT_FOUND body."""
    mug_id = _lines(client, "ORD-1001", "asha@example.com")["MUG-001"]["line_id"]
    line = [{"line_id": mug_id, "quantity": 1}]
    state = _db_state(db_path)
    unknown = _return(client, "ORD-9999", "asha@example.com", line)
    wrong = _return(client, "ORD-1001", "ben@example.com", line)
    assert unknown.status_code == wrong.status_code == 404
    assert unknown.content == wrong.content
    assert unknown.json()["error"]["code"] == "ORDER_NOT_FOUND"
    assert _db_state(db_path) == state


@pytest.mark.parametrize(
    "payload",
    [
        {"order_id": "ORD-1001", "email": "asha@example.com", "lines": []},
        {"order_id": "ORD-1001", "email": "asha@example.com",
         "lines": [{"line_id": 1, "quantity": 1}, {"line_id": 1, "quantity": 1}]},
        {"order_id": "ORD-1001", "email": "asha@example.com",
         "lines": [{"line_id": 1, "quantity": "lots"}]},
        {"order_id": "ORD-1001", "email": "asha@example.com",
         "lines": [{"line_id": 1, "quantity": 1.5}]},
        {"order_id": "ORD-1001", "lines": [{"line_id": 1, "quantity": 1}]},
        {"order_id": "ORD-1001", "email": "asha@example.com", "lines": [{"quantity": 1}]},
        {"order_id": "ORD-1001", "email": "asha@example.com",
         "lines": [{"line_id": 1, "quantity": 1}], "reason": "x" * 501},
    ],
)
def test_malformed_body_is_validation_error(
    client: TestClient, db_path: Path, payload: dict
) -> None:
    """FR3 / NFR3: empty lines, duplicate line_id, bad types or missing fields are rejected."""
    state = _db_state(db_path)
    response = client.post("/returns", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert _db_state(db_path) == state


def test_lookup_after_returns(client: TestClient) -> None:
    """FR2: lookup lists each Return with its refund_cents and reduces returnable_quantity."""
    lines = _lines(client, "ORD-1001", "asha@example.com")
    mug_id, bag_id = lines["MUG-001"]["line_id"], lines["BAG-003"]["line_id"]
    first = _return(client, "ORD-1001", "asha@example.com",
                    [{"line_id": mug_id, "quantity": 1}], reason="Cracked").json()

    body = client.post(
        "/orders/lookup", json={"order_id": "ORD-1001", "email": "asha@example.com"}
    ).json()
    assert {k: v for k, v in first.items() if k != "order_id"} == body["returns"][0]
    by_sku = {line["sku"]: line for line in body["lines"]}
    assert by_sku["MUG-001"]["returnable_quantity"] == 1
    assert by_sku["BAG-003"]["returnable_quantity"] == 1
    assert body["is_returnable"] is True

    _return(client, "ORD-1001", "asha@example.com",
            [{"line_id": mug_id, "quantity": 1}, {"line_id": bag_id, "quantity": 1}])
    body = client.post(
        "/orders/lookup", json={"order_id": "ORD-1001", "email": "asha@example.com"}
    ).json()
    assert [r["refund_cents"] for r in body["returns"]] == [1250, 2149]
    assert all(line["returnable_quantity"] == 0 for line in body["lines"])
    assert body["is_returnable"] is False


def test_existing_db_gains_return_tables(tmp_path: Path, fixed_clock) -> None:
    """FR3 / AD-7: a database created before story 2.1 gets the new tables on restart."""
    from app.infra.settings import Settings
    from app.main import create_app

    db_path = tmp_path / "old.db"
    with TestClient(create_app(Settings(db_path=db_path), fixed_clock)):
        pass
    conn = sqlite3.connect(db_path)
    conn.executescript("DROP TABLE return_lines; DROP TABLE returns;")
    conn.close()
    with TestClient(create_app(Settings(db_path=db_path), fixed_clock)) as client:
        mug_id = _lines(client, "ORD-1001", "asha@example.com")["MUG-001"]["line_id"]
        response = _return(
            client, "ORD-1001", "asha@example.com", [{"line_id": mug_id, "quantity": 1}]
        )
        assert response.status_code == 201
