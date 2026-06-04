"""Tests for InvoiceParser."""

from datetime import UTC, datetime, timedelta

import pytest

from aqualia.api import InvoiceParser


def _doc(
    total: float = 50.0,
    pending: float = 0.0,
    period: str = "Ene-Feb / 2026",
    status: str = "Pagado",
    issue_date: str = "2026-02-20T00:00:00",
    due_date: str = "2026-04-21T00:00:00",
    paid: bool = True,
) -> dict:
    return {
        "TotalAmount": total,
        "PendingAmount": pending,
        "Period": period,
        "Status": status,
        "IssueDate": issue_date,
        "DueDate": due_date,
        "Paid": paid,
    }


# Six invoices mirroring the real API response (newest first after parsing)
REAL_DOCS = [
    _doc(52.77, period="Mar-Abr / 2026", issue_date="2026-04-22T00:00:00", due_date="2026-06-23T00:00:00"),
    _doc(52.77, period="Ene-Feb / 2026", issue_date="2026-02-20T00:00:00", due_date="2026-04-21T00:00:00"),
    _doc(51.64, period="Nov-Dic / 2025", issue_date="2025-12-17T00:00:00", due_date="2026-02-16T00:00:00"),
    _doc(53.88, period="Sep-Oct / 2025", issue_date="2025-10-21T00:00:00", due_date="2025-12-20T00:00:00"),
    _doc(53.88, period="Jul-Ago / 2025", issue_date="2025-08-19T00:00:00", due_date="2025-10-20T00:00:00"),
    _doc(52.34, period="May-Jun / 2025", issue_date="2025-06-25T00:00:00", due_date="2025-08-24T00:00:00"),
]


class TestEmptyDocuments:
    def test_all_keys_present_and_none(self):
        result = InvoiceParser([]).parse()
        assert result["latest_invoice_amount"] is None
        assert result["latest_invoice_period"] is None
        assert result["latest_invoice_due_date"] is None
        assert result["latest_invoice_status"] is None
        assert result["pending_invoice_amount"] is None
        assert result["avg_invoice_amount"] is None
        assert result["water_price_per_m3"] is None


class TestLatestInvoice:
    def test_returns_most_recent_by_issue_date(self):
        # Give docs out of order; parser must sort newest-first
        docs = [
            _doc(40.0, issue_date="2025-06-01T00:00:00"),
            _doc(60.0, issue_date="2026-04-01T00:00:00"),
        ]
        result = InvoiceParser(docs).parse()
        assert result["latest_invoice_amount"] == pytest.approx(60.0)

    def test_latest_period_string(self):
        result = InvoiceParser(REAL_DOCS).parse()
        assert result["latest_invoice_period"] == "Mar-Abr / 2026"

    def test_latest_status(self):
        result = InvoiceParser(REAL_DOCS).parse()
        assert result["latest_invoice_status"] == "Pagado"

    def test_latest_due_date_is_datetime(self):
        result = InvoiceParser(REAL_DOCS).parse()
        assert isinstance(result["latest_invoice_due_date"], datetime)
        assert result["latest_invoice_due_date"].tzinfo is not None

    def test_latest_due_date_correct_value(self):
        result = InvoiceParser(REAL_DOCS).parse()
        expected = datetime(2026, 6, 23, tzinfo=UTC)
        assert result["latest_invoice_due_date"] == expected

    def test_latest_amount_rounded(self):
        docs = [_doc(52.7777)]
        result = InvoiceParser(docs).parse()
        # latest_invoice_amount is NOT rounded by InvoiceParser itself
        # (value_fn in sensor.py rounds at display time)
        assert result["latest_invoice_amount"] == 52.7777

    def test_unpaid_invoice_reflected_in_status(self):
        docs = [_doc(50.0, pending=50.0, status="Pendiente", paid=False)]
        result = InvoiceParser(docs).parse()
        assert result["latest_invoice_status"] == "Pendiente"


class TestPendingAmount:
    def test_all_paid_sums_to_zero(self):
        result = InvoiceParser(REAL_DOCS).parse()
        assert result["pending_invoice_amount"] == pytest.approx(0.0)

    def test_sums_all_pending_amounts(self):
        docs = [
            _doc(50.0, pending=50.0),
            _doc(50.0, pending=25.0),
            _doc(50.0, pending=0.0),
        ]
        result = InvoiceParser(docs).parse()
        assert result["pending_invoice_amount"] == pytest.approx(75.0)


class TestAvgInvoiceAmount:
    def test_single_document(self):
        result = InvoiceParser([_doc(52.77)]).parse()
        assert result["avg_invoice_amount"] == pytest.approx(52.77)

    def test_average_of_multiple(self):
        docs = [_doc(50.0), _doc(60.0), _doc(70.0)]
        result = InvoiceParser(docs).parse()
        assert result["avg_invoice_amount"] == pytest.approx(60.0)

    def test_real_data_average(self):
        result = InvoiceParser(REAL_DOCS).parse()
        # (52.77 * 2 + 51.64 + 53.88 * 2 + 52.34) / 6
        expected = (52.77 + 52.77 + 51.64 + 53.88 + 53.88 + 52.34) / 6
        assert result["avg_invoice_amount"] == pytest.approx(expected, rel=1e-3)


class TestWaterPrice:
    def test_none_when_no_avg_daily(self):
        result = InvoiceParser(REAL_DOCS, avg_daily_liters=None).parse()
        assert result["water_price_per_m3"] is None

    def test_none_when_avg_daily_zero(self):
        result = InvoiceParser(REAL_DOCS, avg_daily_liters=0.0).parse()
        assert result["water_price_per_m3"] is None

    def test_price_computed_from_avg_and_period(self):
        # Single invoice of 60€, billing period 60 days, 100 L/day
        # estimated m³ = 100 * 60 / 1000 = 6 m³ → price = 60/6 = 10 €/m³
        docs = [_doc(60.0, issue_date="2026-02-01T00:00:00")]
        result = InvoiceParser(docs, avg_daily_liters=100.0).parse()
        # With single doc, billing period defaults to 61 days
        expected = 60.0 / (100.0 * 61 / 1000)
        assert result["water_price_per_m3"] == pytest.approx(expected, rel=1e-3)

    def test_price_uses_avg_invoice_amount(self):
        # Two invoices: 50 and 70 → avg 60. Period 60 days at 100 L/day = 6 m³
        # Expected: 60 / 6 = 10 €/m³
        docs = [
            _doc(50.0, issue_date="2026-04-01T00:00:00"),
            _doc(70.0, issue_date="2026-02-01T00:00:00"),
        ]
        result = InvoiceParser(docs, avg_daily_liters=100.0).parse()
        # period = (2026-04-01 - 2026-02-01).days = 59 days
        period = 59
        avg = 60.0
        expected = avg / (100.0 * period / 1000)
        assert result["water_price_per_m3"] == pytest.approx(expected, rel=1e-3)

    def test_price_positive_with_real_data(self):
        # avg ~100 L/day, avg invoice ~52.88€ → positive price
        result = InvoiceParser(REAL_DOCS, avg_daily_liters=100.0).parse()
        assert result["water_price_per_m3"] is not None
        assert result["water_price_per_m3"] > 0


class TestBillingPeriod:
    def test_single_doc_uses_default_period(self):
        docs = [_doc(50.0, issue_date="2026-04-01T00:00:00")]
        parser = InvoiceParser(docs, avg_daily_liters=100.0)
        assert parser._billing_period_days() == InvoiceParser._TYPICAL_BILLING_DAYS

    def test_two_docs_uses_gap(self):
        docs = [
            _doc(issue_date="2026-04-01T00:00:00"),
            _doc(issue_date="2026-02-01T00:00:00"),
        ]
        parser = InvoiceParser(docs)
        # gap = (Apr 1 - Feb 1) = 59 days
        assert parser._billing_period_days() == 59

    def test_real_data_period_is_roughly_bimonthly(self):
        parser = InvoiceParser(REAL_DOCS)
        period = parser._billing_period_days()
        assert 55 <= period <= 70  # typical bimestral range


class TestSorting:
    def test_sorted_newest_first_regardless_of_input_order(self):
        docs = [
            _doc(30.0, issue_date="2025-06-01T00:00:00"),
            _doc(50.0, issue_date="2026-04-01T00:00:00"),
            _doc(40.0, issue_date="2025-12-01T00:00:00"),
        ]
        parser = InvoiceParser(docs)
        issue_dates = [d["IssueDate"] for d in parser.documents]
        assert issue_dates == sorted(issue_dates, reverse=True)

    def test_latest_amount_is_from_most_recent(self):
        docs = [
            _doc(30.0, issue_date="2025-06-01T00:00:00"),
            _doc(50.0, issue_date="2026-04-01T00:00:00"),
        ]
        result = InvoiceParser(docs).parse()
        assert result["latest_invoice_amount"] == pytest.approx(50.0)
