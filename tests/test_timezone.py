"""Calendar-bound metrics must use Home Assistant's timezone, not UTC.

For a peninsular Spain user (UTC+1/+2) a reading timestamped just after local
midnight falls on the *previous* day in UTC.  With UTC boundaries, "consumed
today" showed yesterday's figure until the offset elapsed, and on the 1st of
the month "consumed this month" summed the whole previous month.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from aqualia.api import ConsumptionParser
from aqualia.coordinator import get_option, resolve_timezone

MADRID = ZoneInfo("Europe/Madrid")


def _reading(dt: datetime, value: float) -> dict:
    return {
        "DateTimeConsumptionCurve": dt.isoformat(),
        "ConsumptionValue": value,
        "ReadingIndex": 1000.0,
    }


def _just_after_local_midnight(day: datetime) -> datetime:
    """00:30 local — always the previous calendar day in UTC for Madrid."""
    return day.replace(hour=0, minute=30, second=0, microsecond=0)


class TestTodayConsumption:
    def test_reading_after_local_midnight_counts_as_today(self):
        reading = _reading(_just_after_local_midnight(datetime.now(MADRID)), 75.0)
        assert ConsumptionParser([reading], tz=MADRID).parse()["today_consumption"] == pytest.approx(75.0)

    def test_same_reading_is_missed_under_utc_boundaries(self):
        """Documents the old behaviour that the tz parameter fixes."""
        reading = _reading(_just_after_local_midnight(datetime.now(MADRID)), 75.0)
        assert ConsumptionParser([reading], tz=UTC).parse()["today_consumption"] == pytest.approx(0.0)

    def test_yesterday_is_not_counted_as_today(self):
        yesterday = datetime.now(MADRID) - timedelta(days=1)
        reading = _reading(yesterday.replace(hour=12), 75.0)
        assert ConsumptionParser([reading], tz=MADRID).parse()["today_consumption"] == pytest.approx(0.0)

    def test_defaults_to_utc_when_no_tz_given(self):
        assert ConsumptionParser([], tz=None).tz is UTC


class TestMonthlyTotal:
    def test_first_of_month_after_local_midnight_counts(self):
        now = datetime.now(MADRID)
        first = _just_after_local_midnight(now.replace(day=1))
        parsed = ConsumptionParser([_reading(first, 120.0)], tz=MADRID).parse()
        assert parsed["monthly_total"] == pytest.approx(120.0)

    def test_same_reading_falls_outside_the_month_under_utc(self):
        now = datetime.now(MADRID)
        first = _just_after_local_midnight(now.replace(day=1))
        parsed = ConsumptionParser([_reading(first, 120.0)], tz=UTC).parse()
        assert parsed["monthly_total"] == pytest.approx(0.0)

    def test_previous_month_is_excluded(self):
        now = datetime.now(MADRID)
        last_month_end = now.replace(day=1, hour=12) - timedelta(days=1)
        parsed = ConsumptionParser([_reading(last_month_end, 500.0)], tz=MADRID).parse()
        assert parsed["monthly_total"] == pytest.approx(0.0)


class TestResolveTimezone:
    def test_returns_configured_zone(self):
        hass = MagicMock()
        hass.config.time_zone = "Europe/Madrid"
        assert resolve_timezone(hass) == MADRID

    def test_falls_back_to_utc_for_unknown_zone(self):
        hass = MagicMock()
        hass.config.time_zone = "Mars/Olympus_Mons"
        assert resolve_timezone(hass) is UTC

    def test_falls_back_to_utc_when_unset(self):
        hass = MagicMock()
        hass.config.time_zone = None
        assert resolve_timezone(hass) is UTC

    def test_falls_back_to_utc_for_non_string(self):
        """hass.config is a MagicMock in many tests — must not blow up."""
        assert resolve_timezone(MagicMock()) is UTC


class TestGetOption:
    def _entry(self, data=None, options=None) -> MagicMock:
        entry = MagicMock()
        entry.data = data or {}
        entry.options = options or {}
        return entry

    def test_options_win_over_data(self):
        entry = self._entry(data={"poll": 60}, options={"poll": 15})
        assert get_option(entry, "poll", 99) == 15

    def test_falls_back_to_data_when_option_absent(self):
        """Entries created before the options flow keep tunables in data."""
        assert get_option(self._entry(data={"poll": 60}), "poll", 99) == 60

    def test_falls_back_to_default_when_neither_present(self):
        assert get_option(self._entry(), "poll", 99) == 99

    def test_zero_in_options_is_not_treated_as_unset(self):
        assert get_option(self._entry(data={"poll": 60}, options={"poll": 0}), "poll", 99) == 0
