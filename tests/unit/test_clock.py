from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.infra.clock import FixedClock, SystemClock


def test_system_clock_is_utc() -> None:
    """NFR2 / AD-4: the real clock reports timezone-aware UTC time."""
    now = SystemClock().now()
    assert now.utcoffset() == timedelta(0)
    assert SystemClock().today() in {now.date(), now.date() + timedelta(days=1)}


def test_fixed_clock_converts_to_utc_date() -> None:
    """NFR2 / AD-4: a pinned clock gives a controllable UTC date (21:00 UTC-5 is next day)."""
    clock = FixedClock(datetime(2026, 11, 19, 21, 0, tzinfo=timezone(timedelta(hours=-5))))
    assert clock.now() == datetime(2026, 11, 20, 2, 0, tzinfo=UTC)
    assert clock.today() == date(2026, 11, 20)


def test_fixed_clock_rejects_naive_datetime() -> None:
    """NFR2 / AD-4: naive datetimes are refused so time is never ambiguous."""
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 11, 19))  # noqa: DTZ001
