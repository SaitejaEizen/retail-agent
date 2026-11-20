from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_clock
from app.infra.clock import FixedClock

# conftest's fixed clock is 2026-11-19, which is also the seed reference date.
SEED_DAY = datetime(2026, 11, 19, 9, 30, tzinfo=UTC)


def _lookup(client: TestClient, order_id: str, email: str):
    return client.post("/orders/lookup", json={"order_id": order_id, "email": email})


def _at(client: TestClient, days_after_seed: int) -> None:
    clock = FixedClock(SEED_DAY + timedelta(days=days_after_seed))
    client.app.dependency_overrides[get_clock] = lambda: clock


def test_lookup_delivered_order(client: TestClient) -> None:
    """FR1 / FR2: a matching lookup returns status, delivery date, lines, total and eligibility."""
    response = _lookup(client, "ORD-1001", "asha@example.com")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "order_id": "ORD-1001",
        "status": "delivered",
        "delivered_on": "2026-11-07",
        "lines": [
            {"line_id": body["lines"][0]["line_id"], "sku": "MUG-001", "quantity": 2,
             "unit_price_cents": 1250, "returnable_quantity": 2},
            {"line_id": body["lines"][1]["line_id"], "sku": "BAG-003", "quantity": 1,
             "unit_price_cents": 899, "returnable_quantity": 1},
        ],
        "total_cents": 3399,
        "return_window_ends_on": "2026-12-07",
        "is_returnable": True,
        "returns": [],
    }
    assert all(isinstance(line["line_id"], int) for line in body["lines"])


def test_lookup_email_ignores_case(client: TestClient) -> None:
    """FR1: the email matches regardless of letter case or surrounding spaces."""
    exact = _lookup(client, "ORD-1001", "asha@example.com").json()
    assert _lookup(client, "ORD-1001", "  ASHA@Example.Com ").json() == exact


def test_unknown_id_and_wrong_email_give_identical_404(client: TestClient) -> None:
    """FR1: unknown order ID and wrong email return byte-identical 404 ORDER_NOT_FOUND bodies."""
    unknown = _lookup(client, "ORD-9999", "asha@example.com")
    wrong_email = _lookup(client, "ORD-1001", "ben@example.com")
    assert unknown.status_code == wrong_email.status_code == 404
    assert unknown.content == wrong_email.content
    assert unknown.json() == {"error": {"code": "ORDER_NOT_FOUND", "message": "Order not found."}}


@pytest.mark.parametrize(("days_after_seed", "expected"), [(-1, True), (0, True), (1, False)])
def test_day_30_boundary_through_api(
    client: TestClient, days_after_seed: int, expected: bool
) -> None:
    """FR2: ORD-1003 (delivered 30 days before seed day) is returnable on day 29/30, not day 31."""
    _at(client, days_after_seed)
    body = _lookup(client, "ORD-1003", "chen@example.com").json()
    assert body["return_window_ends_on"] == "2026-11-19"
    assert body["is_returnable"] is expected


def test_past_window_order_not_returnable(client: TestClient) -> None:
    """FR2: ORD-1002, delivered 41 days ago, is past the window and not returnable."""
    body = _lookup(client, "ORD-1002", "ben@example.com").json()
    assert body["return_window_ends_on"] == "2026-11-08"
    assert body["is_returnable"] is False


@pytest.mark.parametrize(
    ("order_id", "email", "status"),
    [
        ("ORD-1004", "dana@example.com", "placed"),
        ("ORD-1005", "eli@example.com", "shipped"),
        ("ORD-1006", "fatima@example.com", "cancelled"),
    ],
)
def test_undelivered_orders(client: TestClient, order_id: str, email: str, status: str) -> None:
    """FR2: placed, shipped and cancelled Orders have no window end and are not returnable."""
    body = _lookup(client, order_id, email).json()
    assert body["status"] == status
    assert body["delivered_on"] is None
    assert body["return_window_ends_on"] is None
    assert body["is_returnable"] is False
    assert all(line["returnable_quantity"] == line["quantity"] for line in body["lines"])
    assert body["returns"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"order_id": "ORD-1001"},
        {"email": "asha@example.com"},
        {"order_id": "", "email": "asha@example.com"},
        {"order_id": "ORD-1001", "email": ""},
        {"order_id": 1001, "email": "asha@example.com"},
    ],
)
def test_bad_lookup_body_is_validation_error(client: TestClient, payload: dict) -> None:
    """FR1 / NFR3: missing, empty or mistyped fields give 422 VALIDATION_ERROR."""
    response = client.post("/orders/lookup", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_lookup_email_not_in_url_or_query(client: TestClient) -> None:
    """FR1 / AD-9: the lookup is POST-only, so emails never appear in URLs."""
    response = client.get("/orders/lookup", params={"order_id": "ORD-1001", "email": "a@b.c"})
    assert response.status_code == 405
