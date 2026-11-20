"""Health check use case (FR9)."""

import logging
import sqlite3
from typing import Protocol

from app.domain.errors import DomainError, ErrorCode

logger = logging.getLogger(__name__)


class Pingable(Protocol):
    def ping(self) -> None: ...


class HealthService:
    def __init__(self, repository: Pingable) -> None:
        self._repository = repository

    def check(self) -> None:
        """Return normally if the DB answers a query, else raise DATABASE_UNAVAILABLE."""
        try:
            self._repository.ping()
        except sqlite3.Error as exc:
            logger.warning("Health check failed: %s", exc)
            raise DomainError(ErrorCode.DATABASE_UNAVAILABLE) from exc
