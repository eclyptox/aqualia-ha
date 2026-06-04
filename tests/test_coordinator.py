"""Tests for AqualiaDataUpdateCoordinator logic."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from aqualia.coordinator import AqualiaDataUpdateCoordinator
from aqualia.const import CONF_CONTRACT_NUMBER


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
