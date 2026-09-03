"""Tests for the Aqualia config flow: setup, reauth and options."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aqualia.api import AqualiaApiError, AqualiaAuthError
from aqualia.config_flow import AqualiaConfigFlow, AqualiaOptionsFlow
from aqualia.const import (
    CONF_CAC_CODE,
    CONF_CONTRACT_CODE,
    CONF_CONTRACT_NUMBER,
    CONF_CONTRACT_STATUS,
    CONF_CONTRACT_STATUS_CODE,
    CONF_DAYS_BACK,
    CONF_ENTRY_DATE,
    CONF_INSTALLATION_CODE,
    CONF_MUNICIPALITY_CODE,
    CONF_NIF,
    CONF_POLL_INTERVAL_MINUTES,
)

CONF_PASSWORD = "password"

CONTRACT = {
    "CacCode": 6565462,
    "ContractCode": 111,
    "InstallationCode": 222,
    "ContractNumber": "333",
    "MunicipalityCode": "28079",
    "EntryDate": "2020-01-01",
    "ContractStatusCode": 1,
    "ContractStatus": "Activo",
    "Address": "Calle Falsa 123",
}


class FakeHass:
    """Runs executor jobs inline and records config_entries interactions."""

    def __init__(self) -> None:
        self.config_entries = MagicMock()
        self.config_entries.async_reload = AsyncMock()

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def _flow() -> AqualiaConfigFlow:
    flow = AqualiaConfigFlow()
    flow.hass = FakeHass()
    return flow


def _client(contracts=None, contracts_error=None, metrics_error=None) -> MagicMock:
    client = MagicMock()
    if contracts_error is not None:
        client.get_contracts.side_effect = contracts_error
    else:
        client.get_contracts.return_value = contracts
    if metrics_error is not None:
        client.fetch_metrics.side_effect = metrics_error
    else:
        client.fetch_metrics.return_value = {"last_value": 100.0}
    return client


# ── step: user ───────────────────────────────────────────────────────────────

class TestStepUser:
    @pytest.mark.asyncio
    async def test_shows_form_without_input(self):
        result = await _flow().async_step_user()
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_advances_to_contract_step_on_success(self):
        flow = _flow()
        with patch("aqualia.config_flow.AqualiaClient", return_value=_client([CONTRACT])):
            result = await flow.async_step_user({CONF_NIF: "12345678A", CONF_PASSWORD: "pw"})
        assert result["step_id"] == "contract"
        assert flow._nif == "12345678A"
        assert flow._contracts == [CONTRACT]

    @pytest.mark.asyncio
    async def test_discovery_failure_still_advances_for_manual_entry(self):
        flow = _flow()
        with patch("aqualia.config_flow.AqualiaClient", return_value=_client(None)):
            result = await flow.async_step_user({CONF_NIF: "12345678A", CONF_PASSWORD: "pw"})
        assert result["step_id"] == "contract"
        assert flow._contracts is None
        assert "manualmente" in result["description_placeholders"]["discovery_note"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (AqualiaAuthError("bad"), "invalid_auth"),
            (AqualiaApiError("down"), "cannot_connect"),
            (RuntimeError("boom"), "unknown"),
        ],
    )
    async def test_surfaces_errors(self, error, expected):
        flow = _flow()
        with patch(
            "aqualia.config_flow.AqualiaClient", return_value=_client(contracts_error=error)
        ):
            result = await flow.async_step_user({CONF_NIF: "12345678A", CONF_PASSWORD: "pw"})
        assert result["step_id"] == "user"
        assert result["errors"]["base"] == expected

    @pytest.mark.asyncio
    async def test_client_is_closed_even_on_error(self):
        flow = _flow()
        client = _client(contracts_error=AqualiaAuthError("bad"))
        with patch("aqualia.config_flow.AqualiaClient", return_value=client):
            await flow.async_step_user({CONF_NIF: "12345678A", CONF_PASSWORD: "pw"})
        client.close.assert_called_once()


# ── step: contract ───────────────────────────────────────────────────────────

class TestStepContract:
    def _prepared_flow(self, contracts) -> AqualiaConfigFlow:
        flow = _flow()
        flow._nif = "12345678A"
        flow._password = "pw"
        flow._contracts = contracts
        return flow

    @pytest.mark.asyncio
    async def test_selector_resolves_full_contract_identifier(self):
        """The invoice API needs all 8 fields, not just the 4 consumption ones."""
        flow = self._prepared_flow([CONTRACT])
        with patch("aqualia.config_flow.AqualiaClient", return_value=_client()):
            result = await flow.async_step_contract({"contract_selector": "333"})

        assert result["type"] == "create_entry"
        data = result["data"]
        assert data[CONF_CAC_CODE] == 6565462
        assert data[CONF_CONTRACT_CODE] == 111
        assert data[CONF_INSTALLATION_CODE] == 222
        assert data[CONF_CONTRACT_NUMBER] == "333"
        assert data[CONF_MUNICIPALITY_CODE] == "28079"
        assert data[CONF_ENTRY_DATE] == "2020-01-01"
        assert data[CONF_CONTRACT_STATUS_CODE] == 1
        assert data[CONF_CONTRACT_STATUS] == "Activo"
        assert data[CONF_NIF] == "12345678A"
        assert data[CONF_PASSWORD] == "pw"

    @pytest.mark.asyncio
    async def test_unique_id_is_nif_plus_contract(self):
        flow = self._prepared_flow([CONTRACT])
        with patch("aqualia.config_flow.AqualiaClient", return_value=_client()):
            await flow.async_step_contract({"contract_selector": "333"})
        assert flow.unique_id == "12345678A_333"

    @pytest.mark.asyncio
    async def test_manual_entry_without_discovery(self):
        flow = self._prepared_flow(None)
        manual = {
            CONF_CAC_CODE: 1,
            CONF_CONTRACT_CODE: 2,
            CONF_INSTALLATION_CODE: 3,
            CONF_CONTRACT_NUMBER: "4",
            CONF_POLL_INTERVAL_MINUTES: 30,
            CONF_DAYS_BACK: 90,
        }
        with patch("aqualia.config_flow.AqualiaClient", return_value=_client()):
            result = await flow.async_step_contract(manual)
        assert result["type"] == "create_entry"
        assert result["data"][CONF_CONTRACT_NUMBER] == "4"
        assert result["data"][CONF_POLL_INTERVAL_MINUTES] == 30

    @pytest.mark.asyncio
    async def test_validation_failure_reshows_form(self):
        flow = self._prepared_flow([CONTRACT])
        with patch(
            "aqualia.config_flow.AqualiaClient",
            return_value=_client(metrics_error=AqualiaAuthError("bad")),
        ):
            result = await flow.async_step_contract({"contract_selector": "333"})
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_auth"


# ── reauth ───────────────────────────────────────────────────────────────────

class TestReauth:
    def _reauth_flow(self):
        entry = MagicMock()
        entry.entry_id = "abc"
        entry.data = {
            CONF_NIF: "12345678A",
            CONF_PASSWORD: "old",
            CONF_CAC_CODE: 1,
            CONF_CONTRACT_CODE: 2,
            CONF_INSTALLATION_CODE: 3,
            CONF_CONTRACT_NUMBER: "4",
            CONF_DAYS_BACK: 60,
        }
        flow = _flow()
        flow.context = {"entry_id": "abc"}
        flow.hass.config_entries.async_get_entry.return_value = entry
        return flow, entry

    @pytest.mark.asyncio
    async def test_reauth_shows_confirm_form_with_nif(self):
        flow, entry = self._reauth_flow()
        result = await flow.async_step_reauth(entry.data)
        assert result["step_id"] == "reauth_confirm"
        assert result["description_placeholders"]["nif"] == "12345678A"

    @pytest.mark.asyncio
    async def test_successful_reauth_updates_entry_and_reloads(self):
        flow, entry = self._reauth_flow()
        await flow.async_step_reauth(entry.data)
        with patch("aqualia.config_flow.AqualiaClient", return_value=_client()):
            result = await flow.async_step_reauth_confirm({CONF_PASSWORD: "new"})

        assert result["type"] == "abort"
        assert result["reason"] == "reauth_successful"
        updated = flow.hass.config_entries.async_update_entry.call_args
        assert updated.kwargs["data"][CONF_PASSWORD] == "new"
        # Contract details must survive the password change
        assert updated.kwargs["data"][CONF_CONTRACT_NUMBER] == "4"
        flow.hass.config_entries.async_reload.assert_awaited_once_with("abc")

    @pytest.mark.asyncio
    async def test_wrong_password_does_not_update_entry(self):
        flow, entry = self._reauth_flow()
        await flow.async_step_reauth(entry.data)
        with patch(
            "aqualia.config_flow.AqualiaClient",
            return_value=_client(metrics_error=AqualiaAuthError("bad")),
        ):
            result = await flow.async_step_reauth_confirm({CONF_PASSWORD: "wrong"})

        assert result["errors"]["base"] == "invalid_auth"
        flow.hass.config_entries.async_update_entry.assert_not_called()
        flow.hass.config_entries.async_reload.assert_not_awaited()


# ── options ──────────────────────────────────────────────────────────────────

class TestOptionsFlow:
    def _options_flow(self, data=None, options=None) -> AqualiaOptionsFlow:
        entry = MagicMock()
        entry.data = data or {CONF_POLL_INTERVAL_MINUTES: 60, CONF_DAYS_BACK: 60}
        entry.options = options or {}
        return AqualiaOptionsFlow(entry)

    @pytest.mark.asyncio
    async def test_shows_form_without_input(self):
        result = await self._options_flow().async_step_init()
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_saves_submitted_options(self):
        flow = self._options_flow()
        result = await flow.async_step_init(
            {CONF_POLL_INTERVAL_MINUTES: 15, CONF_DAYS_BACK: 120}
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_POLL_INTERVAL_MINUTES] == 15
        assert result["data"][CONF_DAYS_BACK] == 120

    @pytest.mark.asyncio
    async def test_form_defaults_prefer_existing_options_over_data(self):
        flow = self._options_flow(
            data={CONF_POLL_INTERVAL_MINUTES: 60, CONF_DAYS_BACK: 60},
            options={CONF_POLL_INTERVAL_MINUTES: 15},
        )
        result = await flow.async_step_init()
        defaults = {
            str(key): key.default() for key in result["data_schema"].schema
        }
        assert defaults[CONF_POLL_INTERVAL_MINUTES] == 15
        assert defaults[CONF_DAYS_BACK] == 60

    def test_config_flow_exposes_options_handler(self):
        assert isinstance(
            AqualiaConfigFlow.async_get_options_flow(MagicMock()), AqualiaOptionsFlow
        )
