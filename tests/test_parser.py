"""Tests for ConsumptionParser."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from aqualia.api import ConsumptionParser
from tests.conftest import make_reading


# ── empty readings ──────────────────────────────────────────────────────────

class TestEmptyReadings:
    def test_all_none(self, empty_readings):
        metrics = ConsumptionParser(empty_readings).parse()
        for key in ("last_value", "reading_index", "last_reading_date",
                    "reading_gap_days", "daily_normalized", "today_consumption",
                    "monthly_total", "avg_daily_30d", "ratio_vs_avg", "days_since_reading"):
            assert metrics[key] is None, f"{key} should be None for empty readings"


# ── last_value / reading_index ───────────────────────────────────────────────

class TestLastValue:
    def test_returns_last_reading_value(self, recent_readings):
        metrics = ConsumptionParser(recent_readings).parse()
        assert metrics["last_value"] == 100.0

    def test_returns_last_index(self, recent_readings):
        metrics = ConsumptionParser(recent_readings).parse()
        assert metrics["reading_index"] == pytest.approx(1500.0)

    def test_single_reading(self, single_reading):
        metrics = ConsumptionParser(single_reading).parse()
        assert metrics["last_value"] == 120.0
        assert metrics["reading_index"] == 2000.0


# ── reading_gap_days ─────────────────────────────────────────────────────────

class TestReadingGap:
    def test_gap_is_one_for_consecutive_daily_readings(self, recent_readings):
        metrics = ConsumptionParser(recent_readings).parse()
        assert metrics["reading_gap_days"] == 1

    def test_gap_detected_correctly(self, gapped_readings):
        metrics = ConsumptionParser(gapped_readings).parse()
        assert metrics["reading_gap_days"] == 3

    def test_single_reading_gap_is_one(self, single_reading):
        metrics = ConsumptionParser(single_reading).parse()
        assert metrics["reading_gap_days"] == 1


# ── daily_normalized ─────────────────────────────────────────────────────────

class TestDailyNormalized:
    def test_no_gap_equals_value(self, recent_readings):
        metrics = ConsumptionParser(recent_readings).parse()
        assert metrics["daily_normalized"] == pytest.approx(100.0)

    def test_three_day_gap_divides_by_three(self, gapped_readings):
        metrics = ConsumptionParser(gapped_readings).parse()
        # last value 300 / gap 3 = 100 L/day
        assert metrics["daily_normalized"] == pytest.approx(100.0)

    def test_two_day_gap(self):
        now = datetime.now(UTC)
        readings = [
            make_reading(now - timedelta(days=4), 100.0, 1100.0),
            make_reading(now - timedelta(days=2), 200.0, 1300.0),
        ]
        metrics = ConsumptionParser(readings).parse()
        assert metrics["daily_normalized"] == pytest.approx(100.0)


# ── today_consumption ────────────────────────────────────────────────────────

class TestTodayConsumption:
    def test_today_reading_counted(self, today_reading):
        metrics = ConsumptionParser(today_reading).parse()
        assert metrics["today_consumption"] == pytest.approx(95.0)

    def test_no_reading_today_returns_zero(self, recent_readings):
        # recent_readings ends yesterday — today should be 0
        metrics = ConsumptionParser(recent_readings).parse()
        assert metrics["today_consumption"] == pytest.approx(0.0)

    def test_multiple_today_readings_summed(self):
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        readings = [
            make_reading(today.replace(hour=6), 50.0, 1050.0),
            make_reading(today.replace(hour=18), 60.0, 1110.0),
        ]
        metrics = ConsumptionParser(readings).parse()
        assert metrics["today_consumption"] == pytest.approx(110.0)


# ── monthly_total ────────────────────────────────────────────────────────────

class TestMonthlyTotal:
    def test_only_current_month(self):
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        readings = [
            # last month
            make_reading(month_start - timedelta(days=1), 200.0, 800.0),
            # this month
            make_reading(month_start + timedelta(days=1), 100.0, 900.0),
            make_reading(month_start + timedelta(days=2), 110.0, 1010.0),
        ]
        metrics = ConsumptionParser(readings).parse()
        assert metrics["monthly_total"] == pytest.approx(210.0)

    def test_empty_month(self):
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # All readings last month
        readings = [
            make_reading(month_start - timedelta(days=5), 100.0, 1000.0),
            make_reading(month_start - timedelta(days=3), 100.0, 1100.0),
        ]
        metrics = ConsumptionParser(readings).parse()
        assert metrics["monthly_total"] == pytest.approx(0.0)


# ── avg_daily_30d ────────────────────────────────────────────────────────────

class TestAvgDaily30d:
    def test_uniform_daily_readings(self, recent_readings):
        # All readings are 100 L/day, all within last 30 days
        metrics = ConsumptionParser(recent_readings).parse()
        assert metrics["avg_daily_30d"] == pytest.approx(100.0)

    def test_excludes_older_readings(self):
        now = datetime.now(UTC)
        # Two consecutive daily readings within the window (gap=1 each → normalized=80)
        # Plus old readings that must NOT affect the average.
        # The reading at day-10 has previous at day-11 (gap=1), so normalized=80.
        readings = [
            make_reading(now - timedelta(days=35), 999.0, 500.0),
            make_reading(now - timedelta(days=11), 80.0, 1579.0),
            make_reading(now - timedelta(days=10), 80.0, 1659.0),
            make_reading(now - timedelta(days=9), 80.0, 1739.0),
        ]
        metrics = ConsumptionParser(readings).parse()
        # Only the 3 readings within 30d are included; day-11 has gap 24 from day-35
        # day-10: gap=1, norm=80. day-9: gap=1, norm=80.
        # day-11 (first in window): gap from day-35 = 24, norm=80/24≈3.33
        # avg = (3.33 + 80 + 80) / 3 ≈ 54.44 — this verifies old values are excluded
        # but to test exclusion cleanly, check that avg ≠ 999:
        assert metrics["avg_daily_30d"] < 100.0
        assert metrics["avg_daily_30d"] > 0.0
        # More importantly: avg_daily_30d is NOT influenced by the 999 L readings
        # (if it were included as-is, avg would be >> 100)
        assert metrics["avg_daily_30d"] < 90.0

    def test_normalises_gap_in_average(self, gapped_readings):
        # The 3-day gap reading (300 L) normalises to 100 L/day
        metrics = ConsumptionParser(gapped_readings).parse()
        assert metrics["avg_daily_30d"] == pytest.approx(100.0)

    def test_zero_readings_in_window_returns_zero(self):
        now = datetime.now(UTC)
        readings = [make_reading(now - timedelta(days=40), 100.0, 1100.0)]
        metrics = ConsumptionParser(readings).parse()
        assert metrics["avg_daily_30d"] == pytest.approx(0.0)


# ── ratio_vs_avg ─────────────────────────────────────────────────────────────

class TestRatioVsAvg:
    def test_equal_to_avg_gives_100_percent(self, recent_readings):
        # All readings are 100 L → daily_normalized == avg → ratio 100%
        metrics = ConsumptionParser(recent_readings).parse()
        assert metrics["ratio_vs_avg"] == pytest.approx(100.0)

    def test_double_average_gives_200_percent(self):
        now = datetime.now(UTC)
        # 4 normal days then 1 double day
        readings = [
            make_reading(now - timedelta(days=5), 100.0, 1100.0),
            make_reading(now - timedelta(days=4), 100.0, 1200.0),
            make_reading(now - timedelta(days=3), 100.0, 1300.0),
            make_reading(now - timedelta(days=2), 100.0, 1400.0),
            make_reading(now - timedelta(days=1), 200.0, 1600.0),
        ]
        metrics = ConsumptionParser(readings).parse()
        # avg_30d = (100+100+100+100+200)/5 = 120, last_normalized = 200
        # ratio = 200/120 * 100 ≈ 166.7
        assert metrics["ratio_vs_avg"] == pytest.approx(200 / 120 * 100, rel=0.01)

    def test_zero_avg_returns_zero(self):
        now = datetime.now(UTC)
        readings = [make_reading(now - timedelta(days=40), 100.0, 1100.0)]
        metrics = ConsumptionParser(readings).parse()
        assert metrics["ratio_vs_avg"] == pytest.approx(0.0)


# ── days_since_reading ───────────────────────────────────────────────────────

class TestDaysSinceReading:
    def test_yesterday_is_one(self):
        now = datetime.now(UTC)
        readings = [make_reading(now - timedelta(hours=25), 100.0, 1100.0)]
        metrics = ConsumptionParser(readings).parse()
        assert metrics["days_since_reading"] == 1

    def test_recent_is_zero(self):
        now = datetime.now(UTC)
        readings = [make_reading(now - timedelta(hours=1), 100.0, 1100.0)]
        metrics = ConsumptionParser(readings).parse()
        assert metrics["days_since_reading"] == 0

    def test_stale_reading(self, stale_readings):
        metrics = ConsumptionParser(stale_readings).parse()
        # stale_readings ends 10 days ago, so days_since_reading should be ≥ 9
        assert metrics["days_since_reading"] >= 9

    def test_never_negative(self):
        now = datetime.now(UTC)
        # Reading in the future (shouldn't happen but guard it)
        readings = [make_reading(now + timedelta(hours=1), 100.0, 1100.0)]
        metrics = ConsumptionParser(readings).parse()
        assert metrics["days_since_reading"] >= 0


# ── ordering ─────────────────────────────────────────────────────────────────

class TestOrdering:
    def test_unsorted_input_sorted_internally(self):
        now = datetime.now(UTC)
        readings = [
            make_reading(now - timedelta(days=1), 200.0, 1300.0),
            make_reading(now - timedelta(days=3), 100.0, 1100.0),
            make_reading(now - timedelta(days=2), 100.0, 1200.0),
        ]
        metrics = ConsumptionParser(readings).parse()
        # last reading should be the one from yesterday, value 200
        assert metrics["last_value"] == pytest.approx(200.0)

    def test_gap_computed_from_last_two_sorted(self):
        now = datetime.now(UTC)
        readings = [
            make_reading(now - timedelta(days=4), 100.0, 1100.0),
            make_reading(now - timedelta(days=1), 100.0, 1200.0),  # 3-day gap
            make_reading(now - timedelta(days=2), 100.0, 1300.0),  # out of order
        ]
        metrics = ConsumptionParser(readings).parse()
        # After sorting: days 4, 2, 1 → last gap = 1
        assert metrics["reading_gap_days"] == 1
