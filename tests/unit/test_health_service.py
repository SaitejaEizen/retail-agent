import sqlite3

import pytest

from app.domain.errors import DomainError, ErrorCode
from app.services.health_service import HealthService


class _Repo:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    def ping(self) -> None:
        self.calls += 1
        if self.error:
            raise self.error


def test_check_passes_when_ping_succeeds() -> None:
    """FR9: the health check runs a real DB query and succeeds when it answers."""
    repo = _Repo()
    HealthService(repo).check()
    assert repo.calls == 1


def test_check_maps_db_failure_to_database_unavailable() -> None:
    """FR9 / AD-6: any sqlite3 error becomes DATABASE_UNAVAILABLE."""
    with pytest.raises(DomainError) as info:
        HealthService(_Repo(sqlite3.OperationalError("no such table: orders"))).check()
    assert info.value.code is ErrorCode.DATABASE_UNAVAILABLE
