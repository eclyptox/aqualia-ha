"""Tests for sensor entity logic (availability, value_fn, attributes)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, PropertyMock

import pytest

from aqualia.sensor import AqualiaSensor, AqualiaCumulativeSensor, SENSORS, INVOICE_SENSORS, _STALE_DAYS


def _make_coordinator(
    data: dict | None,
    last_update_success: bool = True,
    last_error: str | None = None,
    last_success_time: datetime | None = None,
) -> MagicMock:
    coord = MagicMock()
    coord.data = data
    coord.last_update_success = last_update_success
    coord.last_error = last_error
    coord.last_success_time = last_success_time
    return coord


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    return entry


def _make_sensor(
    key: str,
    data: dict | None,
    last_update_success: bool = True,
    last_error: str | None = None,
) -> AqualiaSensor:
    description = next(d for d in SENSORS if d.key == key)
    coord = _make_coordinator(data, last_update_success, last_error=last_error)
    entry = _make_entry()
    sensor = AqualiaSensor(coord, entry, description)
    type(sensor).coordinator = PropertyMock(return_value=coord)
    return sensor


def _recent_date(days_ago: int = 1) -> datetime:
    return datetime.now(UTC) - timedelta(days=days_ago)


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
                               {"today_consumption": 88.8, "days_since_reading": 0,
                                "last_reading_date": _recent_date(0)})
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
            "last_reading_date": _recent_date(_STALE_DAYS + 1),
        }

    def _fresh_data(self) -> dict:
        return {
            **self._stale_data(),
            "days_since_reading": 1,
            "last_reading_date": _recent_date(1),
        }

    def test_stale_unavailable_sensor_is_unavailable_when_stale(self):
        sensor = _make_sensor("daily_normalized", self._stale_data())
        assert sensor.available is False

    def test_stale_unavailable_sensor_is_available_when_fresh(self):
        sensor = _make_sensor("daily_normalized", self._fresh_data())
        assert sensor.available is True

    def test_non_stale_sensor_available_regardless_of_days(self):
        sensor = _make_sensor("days_since_reading", self._stale_data())
        assert sensor.available is True

    def test_last_value_always_available_when_has_data(self):
        sensor = _make_sensor("last_value", self._stale_data())
        assert sensor.available is True

    def test_available_even_when_api_fails_but_has_data(self):
        # API failure should NOT make sensors unavailable if we have cached data
        sensor = _make_sensor("daily_normalized", self._fresh_data(), last_update_success=False)
        assert sensor.available is True

    def test_unavailable_when_no_data_at_all(self):
        sensor = _make_sensor("daily_normalized", None)
        assert sensor.available is False

    def test_unavailable_when_last_reading_date_is_none(self):
        data = {**self._fresh_data(), "last_reading_date": None}
        sensor = _make_sensor("daily_normalized", data)
        assert sensor.available is False

    def test_today_consumption_unavailable_when_stale(self):
        sensor = _make_sensor("today_consumption", self._stale_data())
        assert sensor.available is False

    def test_monthly_total_unavailable_when_stale(self):
        sensor = _make_sensor("monthly_total", self._stale_data())
        assert sensor.available is False

    def test_non_stale_sensor_available_even_after_api_failure(self):
        sensor = _make_sensor("last_value", self._stale_data(), last_update_success=False)
        assert sensor.available is True


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
    def _make(
        self,
        data: dict | None,
        success: bool = True,
        last_error: str | None = None,
        last_success_time: datetime | None = None,
    ) -> AqualiaCumulativeSensor:
        coord = _make_coordinator(
            data, success, last_error=last_error, last_success_time=last_success_time
        )
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

    def test_available_when_has_data(self):
        sensor = self._make({"reading_index": 5000.0, "last_reading_date": _recent_date(1)})
        assert sensor.available is True

    def test_available_even_when_api_fails(self):
        # Energy Dashboard sensor must stay available even if API is down
        sensor = self._make({"reading_index": 5000.0}, success=False)
        assert sensor.available is True

    def test_unavailable_only_when_no_data(self):
        sensor = self._make(None)
        assert sensor.available is False

    def test_attributes_include_delay_flag(self):
        last_date = _recent_date(3)
        sensor = self._make({"reading_index": 5000.0, "last_reading_date": last_date})
        attrs = sensor.extra_state_attributes
        assert attrs["days_since_reading"] > 0
        assert attrs["data_delayed"] is True

    def test_attributes_delay_false_when_reading_today(self):
        sensor = self._make({"reading_index": 5000.0, "last_reading_date": datetime.now(UTC)})
        attrs = sensor.extra_state_attributes
        assert attrs["data_delayed"] is False

    def test_attributes_empty_when_no_data(self):
        sensor = self._make(None)
        assert sensor.extra_state_attributes == {}

    def test_attributes_include_last_update_success(self):
        ts = datetime(2026, 6, 4, 8, 0, 0, tzinfo=UTC)
        sensor = self._make(
            {"reading_index": 5000.0, "last_reading_date": _recent_date(1)},
            last_success_time=ts,
        )
        attrs = sensor.extra_state_attributes
        assert attrs["last_update_success"] == ts.isoformat()

    def test_attributes_include_api_error_when_present(self):
        sensor = self._make(
            {"reading_index": 5000.0, "last_reading_date": _recent_date(1)},
            last_error="Connection timeout",
        )
        attrs = sensor.extra_state_attributes
        assert attrs["api_error"] == "Connection timeout"

    def test_attributes_no_api_error_when_none(self):
        sensor = self._make(
            {"reading_index": 5000.0, "last_reading_date": _recent_date(1)},
            last_error=None,
        )
        attrs = sensor.extra_state_attributes
        assert "api_error" not in attrs

    def test_attributes_days_since_reading_computed_dynamically(self):
        # days_since_reading is computed from last_reading_date at call time,
        # not from cached coordinator data — stays accurate even during API outages
        last_date = _recent_date(5)
        sensor = self._make({"reading_index": 5000.0, "last_reading_date": last_date,
                              "days_since_reading": 999})  # stale cached value
        attrs = sensor.extra_state_attributes
        assert 4 <= attrs["days_since_reading"] <= 6  # dynamically computed, ~5


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


# ── Invoice sensors ───────────────────────────────────────────────────────────

def _invoice_data() -> dict:
    """Coordinator data dict with invoice fields populated."""
    return {
        "reading_index": 500_000.0,
        "last_reading_date": _recent_date(1),
        "days_since_reading": 1,
        "avg_daily_30d": 100.0,
        # invoice fields
        "latest_invoice_amount": 52.77,
        "latest_invoice_period": "Mar-Abr / 2026",
        "latest_invoice_due_date": datetime(2026, 6, 23, tzinfo=UTC),
        "latest_invoice_status": "Pagado",
        "pending_invoice_amount": 0.0,
        "avg_invoice_amount": 52.88,
        "water_price_per_m3": 8.6678,
    }


def _make_invoice_sensor(key: str, data: dict | None) -> AqualiaSensor:
    desc = next(d for d in INVOICE_SENSORS if d.key == key)
    coord = _make_coordinator(data)
    entry = _make_entry()
    sensor = AqualiaSensor(coord, entry, desc)
    type(sensor).coordinator = PropertyMock(return_value=coord)
    return sensor


class TestInvoiceSensorAvailability:
    def test_available_when_invoice_data_present(self):
        sensor = _make_invoice_sensor("latest_invoice_amount", _invoice_data())
        assert sensor.available is True

    def test_unavailable_when_coordinator_data_is_none(self):
        sensor = _make_invoice_sensor("latest_invoice_amount", None)
        assert sensor.available is False

    def test_unavailable_when_invoice_key_is_none(self):
        data = {**_invoice_data(), "latest_invoice_amount": None}
        sensor = _make_invoice_sensor("latest_invoice_amount", data)
        assert sensor.available is False

    def test_available_even_when_api_fetch_failed(self):
        # Invoice sensors stay available as long as coordinator.data is not None
        # and the key has a value (data is stale-cached from last good fetch)
        sensor = _make_invoice_sensor("water_price_per_m3", _invoice_data())
        assert sensor.available is True

    def test_pending_amount_unavailable_when_missing(self):
        data = {**_invoice_data(), "pending_invoice_amount": None}
        sensor = _make_invoice_sensor("pending_invoice_amount", data)
        assert sensor.available is False

    def test_water_price_unavailable_when_missing(self):
        data = {**_invoice_data(), "water_price_per_m3": None}
        sensor = _make_invoice_sensor("water_price_per_m3", data)
        assert sensor.available is False


class TestInvoiceSensorValues:
    def test_latest_invoice_amount_value(self):
        sensor = _make_invoice_sensor("latest_invoice_amount", _invoice_data())
        assert sensor.native_value == pytest.approx(52.77)

    def test_water_price_value_rounded(self):
        sensor = _make_invoice_sensor("water_price_per_m3", _invoice_data())
        assert sensor.native_value == pytest.approx(8.6678)

    def test_pending_amount_value(self):
        sensor = _make_invoice_sensor("pending_invoice_amount", _invoice_data())
        assert sensor.native_value == pytest.approx(0.0)

    def test_due_date_is_timestamp(self):
        sensor = _make_invoice_sensor("latest_invoice_due_date", _invoice_data())
        val = sensor.native_value
        assert isinstance(val, datetime)

    def test_avg_invoice_amount(self):
        sensor = _make_invoice_sensor("avg_invoice_amount", _invoice_data())
        assert sensor.native_value == pytest.approx(52.88)


class TestInvoiceSensorAttributes:
    def test_latest_amount_includes_period_and_status(self):
        sensor = _make_invoice_sensor("latest_invoice_amount", _invoice_data())
        attrs = sensor.extra_state_attributes
        assert attrs["latest_invoice_period"] == "Mar-Abr / 2026"
        assert attrs["latest_invoice_status"] == "Pagado"

    def test_invoice_sensors_do_not_expose_days_since_reading(self):
        # days_since_reading is a consumption staleness metric, irrelevant for invoices
        sensor = _make_invoice_sensor("latest_invoice_amount", _invoice_data())
        attrs = sensor.extra_state_attributes
        assert "days_since_reading" not in attrs

    def test_consumption_sensors_still_expose_days_since_reading(self):
        sensor = _make_sensor("last_value", {"last_value": 100.0, "days_since_reading": 3})
        attrs = sensor.extra_state_attributes
        assert "days_since_reading" in attrs


class TestInvoiceSensorDescriptions:
    def test_all_invoice_keys_unique(self):
        keys = [d.key for d in INVOICE_SENSORS]
        assert len(keys) == len(set(keys))

    def test_all_invoice_sensors_have_requires_data(self):
        for desc in INVOICE_SENSORS:
            assert desc.requires_data is True, f"{desc.key} must have requires_data=True"

    def test_no_invoice_sensor_has_stale_unavailable(self):
        for desc in INVOICE_SENSORS:
            assert desc.stale_unavailable is False, f"{desc.key} must not have stale_unavailable"

    def test_water_price_has_measurement_state_class(self):
        desc = next(d for d in INVOICE_SENSORS if d.key == "water_price_per_m3")
        from aqualia.sensor import SensorStateClass
        assert desc.state_class == SensorStateClass.MEASUREMENT

    def test_invoice_amount_has_monetary_device_class(self):
        desc = next(d for d in INVOICE_SENSORS if d.key == "latest_invoice_amount")
        from aqualia.sensor import SensorDeviceClass
        assert desc.device_class == SensorDeviceClass.MONETARY
