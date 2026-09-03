"""Regression tests: malformed API payloads must never stall the integration.

Aqualia returns explicit nulls and occasionally unparseable dates.  Before
these guards a single bad field raised inside the coordinator, which either
froze every sensor (consumption) or silently pinned invoices to a stale
cache forever.
"""

import pytest

from aqualia.api import ConsumptionParser, InvoiceParser, _parse_datetime, _to_float

GOOD_DATE = "2026-09-01T00:00:00"


def _reading(date=GOOD_DATE, value=100.0, index=1000.0):
    return {
        "DateTimeConsumptionCurve": date,
        "ConsumptionValue": value,
        "ReadingIndex": index,
    }


# ── consumption ──────────────────────────────────────────────────────────────

class TestMalformedReadings:
    def test_null_consumption_value_does_not_raise(self):
        metrics = ConsumptionParser([_reading(value=None)]).parse()
        assert metrics["last_value"] == 0.0

    def test_missing_consumption_value_does_not_raise(self):
        metrics = ConsumptionParser([{"DateTimeConsumptionCurve": GOOD_DATE}]).parse()
        assert metrics["last_value"] == 0.0

    def test_non_numeric_consumption_value_falls_back_to_zero(self):
        metrics = ConsumptionParser([_reading(value="n/a")]).parse()
        assert metrics["last_value"] == 0.0

    def test_numeric_string_is_accepted(self):
        metrics = ConsumptionParser([_reading(value="150.5")]).parse()
        assert metrics["last_value"] == pytest.approx(150.5)

    def test_unparseable_date_is_dropped_not_raised(self):
        metrics = ConsumptionParser([_reading(date="31/12/2026")]).parse()
        assert metrics["last_value"] is None  # treated as "no readings"

    def test_good_readings_survive_a_bad_neighbour(self):
        metrics = ConsumptionParser(
            [_reading(date="garbage", value=999.0), _reading(value=10.0)]
        ).parse()
        assert metrics["last_value"] == pytest.approx(10.0)

    def test_null_date_is_dropped(self):
        metrics = ConsumptionParser([_reading(date=None), _reading(value=42.0)]).parse()
        assert metrics["last_value"] == pytest.approx(42.0)

    def test_none_readings_list_is_handled(self):
        assert ConsumptionParser(None).parse()["last_value"] is None

    def test_zero_reading_index_stays_none(self):
        """Guards the total_increasing spike fix — a transient 0 must not emit."""
        assert ConsumptionParser([_reading(index=0)]).parse()["reading_index"] is None

    def test_null_reading_index_stays_none(self):
        assert ConsumptionParser([_reading(index=None)]).parse()["reading_index"] is None

    def test_readings_are_sorted_regardless_of_input_order(self):
        metrics = ConsumptionParser(
            [_reading(date="2026-09-05T00:00:00", value=50.0),
             _reading(date="2026-09-01T00:00:00", value=10.0)]
        ).parse()
        assert metrics["last_value"] == pytest.approx(50.0)


# ── invoices ─────────────────────────────────────────────────────────────────

class TestMalformedInvoices:
    def test_null_pending_amount_does_not_raise(self):
        parsed = InvoiceParser(
            [{"IssueDate": "2026-01-01", "TotalAmount": 50.0, "PendingAmount": None}]
        ).parse()
        assert parsed["pending_invoice_amount"] == 0.0

    def test_null_issue_date_does_not_break_sorting(self):
        parsed = InvoiceParser(
            [{"IssueDate": None, "TotalAmount": 50.0},
             {"IssueDate": "2026-01-01", "TotalAmount": 40.0}]
        ).parse()
        # The dated document sorts first; the null one is not "latest"
        assert parsed["latest_invoice_amount"] == pytest.approx(40.0)

    def test_null_total_amount_excluded_from_average(self):
        parsed = InvoiceParser(
            [{"IssueDate": "2026-03-01", "TotalAmount": None},
             {"IssueDate": "2026-01-01", "TotalAmount": 40.0}]
        ).parse()
        assert parsed["avg_invoice_amount"] == pytest.approx(40.0)

    def test_empty_document_does_not_raise(self):
        parsed = InvoiceParser([{}]).parse()
        assert parsed["pending_invoice_amount"] == 0.0
        assert parsed["latest_invoice_amount"] is None

    def test_none_documents_list_is_handled(self):
        assert InvoiceParser(None).parse()["latest_invoice_amount"] is None

    def test_unparseable_due_date_becomes_none(self):
        parsed = InvoiceParser(
            [{"IssueDate": "2026-01-01", "TotalAmount": 50.0, "DueDate": "no-es-fecha"}]
        ).parse()
        assert parsed["latest_invoice_due_date"] is None

    def test_billing_period_ignores_unparseable_issue_dates(self):
        parser = InvoiceParser(
            [{"IssueDate": "basura", "TotalAmount": 1.0},
             {"IssueDate": "2026-01-01", "TotalAmount": 1.0}]
        )
        assert parser._billing_period_days() == parser._TYPICAL_BILLING_DAYS


# ── helpers ──────────────────────────────────────────────────────────────────

class TestHelpers:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, 0.0), ("", 0.0), ("abc", 0.0), (5, 5.0), ("7.5", 7.5), (0, 0.0)],
    )
    def test_to_float(self, value, expected):
        assert _to_float(value) == pytest.approx(expected)

    def test_to_float_custom_default(self):
        assert _to_float(None, None) is None

    @pytest.mark.parametrize("value", [None, "", "31/12/2026", "garbage", 0])
    def test_parse_datetime_returns_none_for_unusable(self, value):
        assert _parse_datetime(value) is None

    def test_parse_datetime_assumes_utc_when_naive(self):
        parsed = _parse_datetime("2026-09-01T10:00:00")
        assert parsed.tzinfo is not None
        assert parsed.hour == 10

    def test_parse_datetime_converts_offset_to_utc(self):
        parsed = _parse_datetime("2026-09-01T10:00:00+02:00")
        assert parsed.hour == 8
