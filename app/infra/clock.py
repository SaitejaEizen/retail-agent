"""The only source of the current time (AD-4). Tests inject FixedClock."""

from datetime import UTC, date, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def today(self) -> date: ...


class SystemClock:
    """Real time, always in UTC."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return self.now().date()


class FixedClock:
    """A clock pinned to one instant, for tests and reproducible runs."""

    def __init__(self, instant: datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError("FixedClock needs a timezone-aware datetime")
        self._instant = instant.astimezone(UTC)

    def now(self) -> datetime:
        return self._instant

    def today(self) -> date:
        return self._instant.date()
