import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


def test_healthz_ok(client: TestClient) -> None:
    """FR9: /healthz returns 200 with status and database ok after querying the DB."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_startup_creates_db_and_seeds(client: TestClient, db_path: Path) -> None:
    """FR10: starting the service on an empty location creates the DB and loads the seed."""
    assert db_path.is_file()
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] >= 6
    finally:
        conn.close()


def test_healthz_503_when_db_file_missing(client: TestClient, db_path: Path) -> None:
    """FR9 / AD-6: a missing DB file gives 503 DATABASE_UNAVAILABLE in the error envelope."""
    db_path.unlink()
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert set(response.json()["error"]) == {"code", "message"}
    assert not db_path.exists()


def test_healthz_503_when_schema_missing(client: TestClient, db_path: Path) -> None:
    """FR9 / AD-6: a reachable file without the orders table still reports DATABASE_UNAVAILABLE."""
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("PRAGMA foreign_keys = OFF; DROP TABLE order_lines; DROP TABLE orders;")
    finally:
        conn.close()
    response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "DATABASE_UNAVAILABLE", "message": "The database is unavailable."}
    }


def test_restart_keeps_single_seed(db_path: Path, fixed_clock) -> None:
    """FR10: restarting the app against the same DB does not duplicate seed rows."""
    from app.infra.settings import Settings
    from app.main import create_app

    for _ in range(2):
        with TestClient(create_app(Settings(db_path=db_path), fixed_clock)) as c:
            assert c.get("/healthz").status_code == 200
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 6
    finally:
        conn.close()
