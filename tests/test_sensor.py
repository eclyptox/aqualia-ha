"""Tests for sensor entity logic (availability, value_fn, attributes)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest

from aqualia.sensor import AqualiaSensor, AqualiaCumulativeSensor, SENSORS, _STALE_DAYS


def _make_coordinator(data: dict | None, last_update_success: bool = True) -> MagicMock:
    coord = MagicMock()
    coord.data = data
    coord.last_update_success = last_update_success
    return coord


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    return entry


def _make_sensor(key: str, data: dict | None, last_update_success: bool = True) -> AqualiaSensor:
    description = next(d for d in SENSORS if d.key == key)
    coord = _make_coordinator(data, last_update_success)
    entry = _make_entry()
    sensor = AqualiaSensor(coord, entry, description)
    # Patch CoordinatorEntity.available to use our mock
    type(sensor).coordinator = PropertyMock(return_value=coord)
    return sensor


# ── native_value ─────────────────────────────────────────────────────────────

class TestNativeValue:
    def test_returns_value_from_coordinator_data(self):
        sensor = _make_sensor("last_value", {"last_value": 150.0, "days_since_reading": 1})
        assert sensor.native_value == pytest.approx(150.0)

    def test_value_fn_rounds_correctly(self):
        sensor = _make_sensor("daily_normalized",
                               {"daily_normalized": 123.456, "days_since_reading": 1})
        assert sensor.native_value == pytest.approx(123.5)

    def test_none_when_coordinator_data_is_none(self):
        sensor = _make_sensor("last_value", None)
        assert sensor.native_value is None

    def test_none_when_key_missing(self):
        sensor = _make_sensor("last_value", {"days_since_reading": 1})
        assert sensor.native_value is None

    def test_today_consumption_value(self):
        sensor = _make_sensor("today_consumption",
                               {"today_consumption": 88.8, "days_since_reading": 0})
        assert sensor.native_value == pytest.approx(88.8)


# ── availability ─────────────────────────────────────────────────────────────

class TestAvailability:
    def _stale_data(self) -> dict:
        return {
            "last_value": 100.0,
            "daily_normalized": 100.0,
            "today_consumption": 0.0,
            "monthly_total": 2000.0,
            "ratio_vs_avg": 100.0,
            "days_since_reading": _STALE_DAYS + 1,
        }

    def _fresh_data(self) -> dict:
        return {**self._stale_data(), "days_since_reading": 1}

    def test_stale_unavailable_sensor_is_unavailable_when_stale(self):
        sensor = _make_sensor("daily_normalized", self._stale_data())
        assert sensor.available is False

    def test_stale_unavailable_sensor_is_available_when_fresh(self):
        sensor = _make_sensor("daily_normalized", self._fresh_data())
        assert sensor.available is True

    def test_non_stale_sensor_available_regardless_of_days(self):
        # days_since_reading sensor itself should never go unavailable due to staleness
        sensor = _make_sensor("days_since_reading", self._stale_data())
        assert sensor.available is True

    def test_last_value_always_available_when_fresh_data(self):
        sensor = _make_sensor("last_value", self._stale_data())
        # last_value has stale_unavailable=False
        assert sensor.available is True

    def test_unavailable_when_coordinator_failed(self):
        sensor = _make_sensor("daily_normalized", self._fresh_data(), last_update_success=False)
        assert sensor.available is False

    def test_unavailable_when_days_since_reading_is_none(self):
        data = {**self._fresh_data(), "days_since_reading": None}
        sensor = _make_sensor("daily_normalized", data)
        assert sensor.available is False

    def test_today_consumption_unavailable_when_stale(self):
        sensor = _make_sensor("today_consumption", self._stale_data())
        assert sensor.available is False

    def test_monthly_total_unavailable_when_stale(self):
        sensor = _make_sensor("monthly_total", self._stale_data())
        assert sensor.available is False


# ── extra_state_attributes ────────────────────────────────────────────────────

class TestExtraAttributes:
    def test_includes_days_since_reading(self):
        sensor = _make_sensor("last_value", {"last_value": 100.0, "days_since_reading": 3})
        attrs = sensor.extra_state_attributes
        assert attrs["days_since_reading"] == 3

    def test_empty_when_no_data(self):
        sensor = _make_sensor("last_value", None)
        assert sensor.extra_state_attributes == {}

    def test_empty_when_days_missing(self):
        sensor = _make_sensor("last_value", {"last_value": 100.0})
        assert sensor.extra_state_attributes == {}


# ── AqualiaCumulativeSensor ───────────────────────────────────────────────────

class TestCumulativeSensor:
    def _make(self, data: dict | None, success: bool = True) -> AqualiaCumulativeSensor:
        coord = _make_coordinator(data, success)
        entry = _make_entry()
        sensor = AqualiaCumulativeSensor(coord, entry)
        type(sensor).coordinator = PropertyMock(return_value=coord)
        return sensor

    def test_returns_reading_index(self):
        sensor = self._make({"reading_index": 5000.5, "days_since_reading": 1})
        assert sensor.native_value == pytest.approx(5000.5)

    def test_none_when_no_data(self):
        sensor = self._make(None)
        assert sensor.native_value is None

    def test_none_when_index_missing(self):
        sensor = self._make({"days_since_reading": 1})
        assert sensor.native_value is None

    def test_attributes_include_delay_flag(self):
        sensor = self._make({"reading_index": 5000.0, "days_since_reading": 3,
                              "last_reading_date": datetime(2026, 5, 1, tzinfo=UTC)})
        attrs = sensor.extra_state_attributes
        assert attrs["days_since_reading"] == 3
        assert attrs["data_delayed"] is True

    def test_attributes_delay_false_when_reading_today(self):
        sensor = self._make({"reading_index": 5000.0, "days_since_reading": 0,
                              "last_reading_date": datetime.now(UTC)})
        attrs = sensor.extra_state_attributes
        assert attrs["data_delayed"] is False

    def test_attributes_empty_when_no_data(self):
        sensor = self._make(None)
        assert sensor.extra_state_attributes == {}


# ── sensor descriptions ───────────────────────────────────────────────────────

class TestSensorDescriptions:
    def test_all_keys_unique(self):
        keys = [d.key for d in SENSORS]
        assert len(keys) == len(set(keys))

    def test_today_consumption_sensor_exists(self):
        keys = [d.key for d in SENSORS]
        assert "today_consumption" in keys

    def test_stale_sensors_have_stale_unavailable(self):
        stale_keys = {"today_consumption", "monthly_total", "daily_normalized", "ratio_vs_avg"}
        for desc in SENSORS:
            if desc.key in stale_keys:
                assert desc.stale_unavailable is True, f"{desc.key} should have stale_unavailable=True"

    def test_diagnostic_sensors_not_stale_unavailable(self):
        stable_keys = {"days_since_reading", "reading_gap_days", "last_reading_date",
                       "avg_daily_30d", "last_value"}
        for desc in SENSORS:
            if desc.key in stable_keys:
                assert desc.stale_unavailable is False, f"{desc.key} should NOT have stale_unavailable"
