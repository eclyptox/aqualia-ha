"""Shared fixtures for Aqualia tests."""

# Install HA stubs before any component imports
from tests.ha_stubs import _install as _install_ha_stubs
_install_ha_stubs()

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest


def make_reading(date: datetime, value: float, index: float) -> dict[str, Any]:
    return {
        "DateTimeConsumptionCurve": date.isoformat(),
        "ConsumptionValue": value,
        "ReadingIndex": index,
    }


def readings_around_now(**days_ago_kwargs) -> list[dict[str, Any]]:
    """Build a list of daily readings ending N days ago."""
    end = datetime.now(UTC) - timedelta(**days_ago_kwargs)
    idx = 1000.0
    result = []
    for i in range(5):
        d = end - timedelta(days=4 - i)
        idx += 100.0
        result.append(make_reading(d, 100.0, idx))
    return result


@pytest.fixture
def recent_readings() -> list[dict[str, Any]]:
    """Five daily readings ending yesterday — fresh data."""
    return readings_around_now(days=1)


@pytest.fixture
def stale_readings() -> list[dict[str, Any]]:
    """Five daily readings ending 10 days ago — stale data."""
    return readings_around_now(days=10)


@pytest.fixture
def gapped_readings() -> list[dict[str, Any]]:
    """Readings with a 3-day accumulated gap on the last entry."""
    now = datetime.now(UTC)
    return [
        make_reading(now - timedelta(days=6), 100.0, 1100.0),
        make_reading(now - timedelta(days=5), 100.0, 1200.0),
        # 3-day gap: one reading covers days 4, 3, 2 → 300 L total
        make_reading(now - timedelta(days=2), 300.0, 1500.0),
    ]


@pytest.fixture
def single_reading() -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    return [make_reading(now - timedelta(days=1), 120.0, 2000.0)]


@pytest.fixture
def today_reading() -> list[dict[str, Any]]:
    """A reading dated exactly today."""
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        make_reading(now - timedelta(days=1), 80.0, 900.0),
        make_reading(now, 95.0, 995.0),
    ]


@pytest.fixture
def empty_readings() -> list[dict[str, Any]]:
    return []
