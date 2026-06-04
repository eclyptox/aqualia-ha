"""Tests for AqualiaDataUpdateCoordinator logic."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from aqualia.coordinator import AqualiaDataUpdateCoordinator
from aqualia.const import CONF_CONTRACT_NUMBER, DOMAIN


# ── _should_fetch_invoices ────────────────────────────────────────────────────

class TestShouldFetchInvoices:
    def _coord(self, last_fetch: datetime | None) -> MagicMock:
        coord = MagicMock(spec=AqualiaDataUpdateCoordinator)
        coord._last_invoice_fetch = last_fetch
        return coord

    def test_true_when_never_fetched(self):
        assert AqualiaDataUpdateCoordinator._should_fetch_invoices(self._coord(None)) is True

    def test_true_when_interval_elapsed(self):
        old = datetime.now(UTC) - timedelta(hours=13)
        assert AqualiaDataUpdateCoordinator._should_fetch_invoices(self._coord(old)) is True

    def test_false_when_recently_fetched(self):
        recent = datetime.now(UTC) - timedelta(hours=1)
        assert AqualiaDataUpdateCoordinator._should_fetch_invoices(self._coord(recent)) is False

    def test_boundary_just_before_interval(self):
        almost = datetime.now(UTC) - timedelta(hours=11, minutes=59)
        assert AqualiaDataUpdateCoordinator._should_fetch_invoices(self._coord(almost)) is False

    def test_boundary_just_after_interval(self):
        just_over = datetime.now(UTC) - timedelta(hours=12, minutes=1)
        assert AqualiaDataUpdateCoordinator._should_fetch_invoices(self._coord(just_over)) is True


# ── _resolve_contract_identifier ──────────────────────────────────────────────

def _make_coord(contract_number: str = "300-1/1-000001") -> MagicMock:
    # No spec: entry is an instance attr set in __init__, spec would block access
    coord = MagicMock()
    coord.entry.data = {CONF_CONTRACT_NUMBER: contract_number}
    return coord


def _make_contract(
    number: str = "300-1/1-000001",
    municipality: str = "3063000100",
    entry_date: str = "21/12/2005 9:58:36",
    status_code: int = 3,
    status: str = "Alta definitiva",
) -> dict:
    return {
        "ContractNumber": number,
        "MunicipalityCode": municipality,
        "EntryDate": entry_date,
        "ContractStatusCode": status_code,
        "ContractStatus": status,
    }


class TestResolveContractIdentifier:
    @pytest.mark.asyncio
    async def test_returns_fields_for_matching_contract(self):
        coord = _make_coord()
        coord.hass.async_add_executor_job = AsyncMock(return_value=[_make_contract()])

        result = await AqualiaDataUpdateCoordinator._resolve_contract_identifier(coord)

        assert result == ("3063000100", "21/12/2005 9:58:36", 3, "Alta definitiva")

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_contracts(self):
        coord = _make_coord()
        coord.hass.async_add_executor_job = AsyncMock(return_value=None)

        result = await AqualiaDataUpdateCoordinator._resolve_contract_identifier(coord)

        assert result == ("", "", 0, "")

    @pytest.mark.asyncio
    async def test_returns_empty_when_contract_list_empty(self):
        coord = _make_coord()
        coord.hass.async_add_executor_job = AsyncMock(return_value=[])

        result = await AqualiaDataUpdateCoordinator._resolve_contract_identifier(coord)

        assert result == ("", "", 0, "")

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_matching_contract(self):
        coord = _make_coord("300-1/1-000001")
        coord.hass.async_add_executor_job = AsyncMock(
            return_value=[_make_contract(number="999-9/9-999999")]
        )

        result = await AqualiaDataUpdateCoordinator._resolve_contract_identifier(coord)

        assert result == ("", "", 0, "")

    @pytest.mark.asyncio
    async def test_matches_by_contract_number(self):
        coord = _make_coord("ABC-1/2-000042")
        contracts = [
            _make_contract(number="ZZZ-9/9-000001", municipality="0000001"),
            _make_contract(number="ABC-1/2-000042", municipality="3063000100"),
        ]
        coord.hass.async_add_executor_job = AsyncMock(return_value=contracts)

        municipality, *_ = await AqualiaDataUpdateCoordinator._resolve_contract_identifier(coord)

        assert municipality == "3063000100"

    @pytest.mark.asyncio
    async def test_returns_empty_on_api_exception(self):
        coord = _make_coord()
        coord.hass.async_add_executor_job = AsyncMock(side_effect=Exception("network error"))

        result = await AqualiaDataUpdateCoordinator._resolve_contract_identifier(coord)

        assert result == ("", "", 0, "")

    @pytest.mark.asyncio
    async def test_zero_status_code_coerced_to_int(self):
        coord = _make_coord()
        contract = _make_contract(status_code=None)  # type: ignore[arg-type]
        coord.hass.async_add_executor_job = AsyncMock(return_value=[contract])

        _, _, status_code, _ = await AqualiaDataUpdateCoordinator._resolve_contract_identifier(coord)

        assert status_code == 0
        assert isinstance(status_code, int)


# ── _notify_new_invoice ───────────────────────────────────────────────────────

def _make_notify_coord() -> MagicMock:
    coord = MagicMock()
    coord.hass.bus.async_fire = MagicMock()
    coord.hass.services.async_call = AsyncMock()
    return coord


class TestNotifyNewInvoice:
    @pytest.mark.asyncio
    async def test_fires_domain_event(self):
        coord = _make_notify_coord()
        await AqualiaDataUpdateCoordinator._notify_new_invoice(
            coord, {"latest_invoice_amount": 52.18}, "Mar-Abr / 2026"
        )
        coord.hass.bus.async_fire.assert_called_once()
        event_name, payload = coord.hass.bus.async_fire.call_args[0]
        assert event_name == f"{DOMAIN}_new_invoice"
        assert payload["period"] == "Mar-Abr / 2026"
        assert payload["amount"] == 52.18

    @pytest.mark.asyncio
    async def test_creates_persistent_notification(self):
        coord = _make_notify_coord()
        await AqualiaDataUpdateCoordinator._notify_new_invoice(
            coord, {"latest_invoice_amount": 40.0}, "Ene-Feb / 2026"
        )
        coord.hass.services.async_call.assert_awaited_once()
        _, service, data = coord.hass.services.async_call.call_args[0]
        assert service == "create"
        assert f"{DOMAIN}_new_invoice" == data["notification_id"]
        assert "40.00 €" in data["message"]
        assert "Ene-Feb / 2026" in data["message"]

    @pytest.mark.asyncio
    async def test_event_excludes_none_amount(self):
        coord = _make_notify_coord()
        await AqualiaDataUpdateCoordinator._notify_new_invoice(
            coord, {}, "May-Jun / 2026"
        )
        _, payload = coord.hass.bus.async_fire.call_args[0]
        assert "amount" not in payload

    @pytest.mark.asyncio
    async def test_event_includes_due_date_iso(self):
        coord = _make_notify_coord()
        due = datetime(2026, 5, 15, tzinfo=UTC)
        await AqualiaDataUpdateCoordinator._notify_new_invoice(
            coord, {"latest_invoice_amount": 38.5, "latest_invoice_due_date": due},
            "Mar-Abr / 2026",
        )
        _, payload = coord.hass.bus.async_fire.call_args[0]
        assert payload["due_date"] == due.isoformat()


# ── period change detection in _refresh_invoice_cache ────────────────────────

def _make_refresh_coord(
    last_period: str | None,
    new_period: str,
    amount: float = 55.0,
) -> MagicMock:
    """Coordinator stub wired for _refresh_invoice_cache tests."""
    from aqualia.const import (
        CONF_CAC_CODE, CONF_CONTRACT_CODE, CONF_INSTALLATION_CODE,
        CONF_MUNICIPALITY_CODE, CONF_ENTRY_DATE, CONF_CONTRACT_STATUS_CODE,
        CONF_CONTRACT_STATUS,
    )
    coord = MagicMock()
    coord._last_known_invoice_period = last_period
    coord._last_invoice_fetch = None
    coord._cached_invoice_data = {}
    coord.entry.data = {
        CONF_CAC_CODE: "CAC1",
        CONF_CONTRACT_CODE: "CC1",
        CONF_INSTALLATION_CODE: "IC1",
        CONF_CONTRACT_NUMBER: "300-1/1-000001",
        CONF_MUNICIPALITY_CODE: "3063000100",
        CONF_ENTRY_DATE: "01/01/2020",
        CONF_CONTRACT_STATUS_CODE: 3,
        CONF_CONTRACT_STATUS: "Alta definitiva",
    }
    # Simulate get_invoices returning minimal doc list → InvoiceParser returns new_period
    coord.hass.async_add_executor_job = AsyncMock(return_value=[
        {
            "IssueDate": "2026-04-01T00:00:00",
            "DueDate": "2026-05-01T00:00:00",
            "TotalAmount": amount,
            "Status": "Pagado",
            "Period": new_period,
            "HasDebt": False,
        }
    ])
    coord.hass.bus.async_fire = MagicMock()
    coord.hass.services.async_call = AsyncMock()
    coord._notify_new_invoice = AsyncMock()
    return coord


class TestRefreshInvoicePeriodDetection:
    @pytest.mark.asyncio
    async def test_notifies_when_period_changes(self):
        coord = _make_refresh_coord(last_period="Ene-Feb / 2026", new_period="Mar-Abr / 2026")
        await AqualiaDataUpdateCoordinator._refresh_invoice_cache(coord, avg_daily_30d=None)
        coord._notify_new_invoice.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_notification_on_first_load(self):
        coord = _make_refresh_coord(last_period=None, new_period="Mar-Abr / 2026")
        await AqualiaDataUpdateCoordinator._refresh_invoice_cache(coord, avg_daily_30d=None)
        coord._notify_new_invoice.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_notification_when_period_unchanged(self):
        coord = _make_refresh_coord(last_period="Mar-Abr / 2026", new_period="Mar-Abr / 2026")
        await AqualiaDataUpdateCoordinator._refresh_invoice_cache(coord, avg_daily_30d=None)
        coord._notify_new_invoice.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_updates_known_period_after_fetch(self):
        coord = _make_refresh_coord(last_period=None, new_period="Mar-Abr / 2026")
        await AqualiaDataUpdateCoordinator._refresh_invoice_cache(coord, avg_daily_30d=None)
        # After first load, _last_known_invoice_period should be set
        assert coord._last_known_invoice_period == "Mar-Abr / 2026"
