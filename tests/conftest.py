"""Shared fixtures: a temporary SQLite file and a pinned Clock (NFR2)."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.infra.clock import FixedClock
from app.infra.settings import Settings
from app.main import create_app

REFERENCE_DATE = date(2026, 11, 19)


@pytest.fixture
def fixed_clock() -> FixedClock:
    return FixedClock(datetime(2026, 11, 19, 9, 30, tzinfo=UTC))


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "retail.db"


@pytest.fixture
def client(db_path: Path, fixed_clock: FixedClock) -> Iterator[TestClient]:
    app = create_app(Settings(db_path=db_path), fixed_clock)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
