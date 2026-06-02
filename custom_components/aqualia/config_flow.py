"""Config flow for Aqualia."""

from __future__ import annotations

from functools import partial
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .api import AqualiaApiError, AqualiaAuthError, AqualiaClient
from .const import (
    CONF_CAC_CODE,
    CONF_CONTRACT_CODE,
    CONF_CONTRACT_NUMBER,
    CONF_DAYS_BACK,
    CONF_INSTALLATION_CODE,
    CONF_NIF,
    CONF_POLL_INTERVAL_MINUTES,
    DEFAULT_DAYS_BACK,
    DEFAULT_POLL_INTERVAL_MINUTES,
    DOMAIN,
    MAX_DAYS_BACK,
    MAX_POLL_INTERVAL_MINUTES,
    MIN_DAYS_BACK,
    MIN_POLL_INTERVAL_MINUTES,
)

_ADVANCED_SCHEMA = {
    vol.Optional(
        CONF_POLL_INTERVAL_MINUTES,
        default=DEFAULT_POLL_INTERVAL_MINUTES,
    ): vol.All(
        vol.Coerce(int),
        vol.Range(min=MIN_POLL_INTERVAL_MINUTES, max=MAX_POLL_INTERVAL_MINUTES),
    ),
    vol.Optional(
        CONF_DAYS_BACK,
        default=DEFAULT_DAYS_BACK,
    ): vol.All(
        vol.Coerce(int),
        vol.Range(min=MIN_DAYS_BACK, max=MAX_DAYS_BACK),
    ),
}


class AqualiaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Two-step config flow: credentials → contract selection."""

    VERSION = 1

    def __init__(self) -> None:
        self._nif: str = ""
        self._password: str = ""
        self._contracts: list[dict[str, Any]] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1: validate NIF + password and attempt contract discovery."""

        errors: dict[str, str] = {}
        if user_input is not None:
            client = AqualiaClient(user_input[CONF_NIF], user_input[CONF_PASSWORD])
            try:
                contracts = await self.hass.async_add_executor_job(client.get_contracts)
            except AqualiaAuthError:
                errors["base"] = "invalid_auth"
            except AqualiaApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                self._nif = user_input[CONF_NIF]
                self._password = user_input[CONF_PASSWORD]
                self._contracts = contracts
                return await self.async_step_contract()
            finally:
                await self.hass.async_add_executor_job(client.close)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NIF): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_contract(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2: select discovered contract or enter codes manually."""

        errors: dict[str, str] = {}

        if user_input is not None:
            # When discovery succeeded, resolve contract codes from the stored list
            if self._contracts is not None and "contract_selector" in user_input:
                selected_number = user_input["contract_selector"]
                contract = next(
                    (
                        c
                        for c in self._contracts
                        if str(c.get("ContractNumber", "")) == selected_number
                    ),
                    None,
                )
                if contract is not None:
                    user_input = {
                        CONF_CAC_CODE: int(contract.get("CacCode", 0)),
                        CONF_CONTRACT_CODE: int(contract.get("ContractCode", 0)),
                        CONF_INSTALLATION_CODE: int(contract.get("InstallationCode", 0)),
                        CONF_CONTRACT_NUMBER: selected_number,
                        CONF_POLL_INTERVAL_MINUTES: user_input.get(
                            CONF_POLL_INTERVAL_MINUTES, DEFAULT_POLL_INTERVAL_MINUTES
                        ),
                        CONF_DAYS_BACK: user_input.get(CONF_DAYS_BACK, DEFAULT_DAYS_BACK),
                    }

            data = {CONF_NIF: self._nif, CONF_PASSWORD: self._password, **user_input}

            try:
                await _validate_input(self.hass, data)
            except AqualiaAuthError:
                errors["base"] = "invalid_auth"
            except AqualiaApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    f"{self._nif}_{data[CONF_CONTRACT_NUMBER]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Aqualia {data[CONF_CONTRACT_NUMBER]}",
                    data=data,
                )

        return self.async_show_form(
            step_id="contract",
            data_schema=_contract_schema(self._contracts, user_input),
            errors=errors,
            description_placeholders={
                "discovery_note": (
                    ""
                    if self._contracts is not None
                    else "No se encontraron contratos automáticamente. Introduce los códigos manualmente."
                )
            },
        )


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    client = AqualiaClient(data[CONF_NIF], data[CONF_PASSWORD])
    try:
        await hass.async_add_executor_job(
            partial(
                client.fetch_metrics,
                days_back=data[CONF_DAYS_BACK],
                cac_code=data[CONF_CAC_CODE],
                contract_code=data[CONF_CONTRACT_CODE],
                installation_code=data[CONF_INSTALLATION_CODE],
                contract_number=data[CONF_CONTRACT_NUMBER],
            )
        )
    finally:
        await hass.async_add_executor_job(client.close)


def _contract_schema(
    contracts: list[dict[str, Any]] | None,
    defaults: dict[str, Any] | None,
) -> vol.Schema:
    d = defaults or {}
    if contracts:
        options = {
            str(c.get("ContractNumber", f"contrato_{i}")): _contract_label(c, i)
            for i, c in enumerate(contracts)
        }
        return vol.Schema(
            {
                vol.Required("contract_selector"): vol.In(options),
                **_advanced_defaults(d),
            }
        )
    return vol.Schema(
        {
            vol.Required(CONF_CAC_CODE, default=d.get(CONF_CAC_CODE, 0)): vol.Coerce(int),
            vol.Required(CONF_CONTRACT_CODE, default=d.get(CONF_CONTRACT_CODE, 0)): vol.Coerce(int),
            vol.Required(CONF_INSTALLATION_CODE, default=d.get(CONF_INSTALLATION_CODE, 0)): vol.Coerce(int),
            vol.Required(CONF_CONTRACT_NUMBER, default=d.get(CONF_CONTRACT_NUMBER, "")): str,
            **_advanced_defaults(d),
        }
    )


def _contract_label(contract: dict[str, Any], index: int) -> str:
    number = contract.get("ContractNumber", f"#{index + 1}")
    address = contract.get("Address") or contract.get("address") or contract.get("Direccion")
    return f"{number} — {address}" if address else str(number)


def _advanced_defaults(d: dict[str, Any]) -> dict:
    return {
        vol.Optional(
            CONF_POLL_INTERVAL_MINUTES,
            default=d.get(CONF_POLL_INTERVAL_MINUTES, DEFAULT_POLL_INTERVAL_MINUTES),
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_POLL_INTERVAL_MINUTES, max=MAX_POLL_INTERVAL_MINUTES),
        ),
        vol.Optional(
            CONF_DAYS_BACK,
            default=d.get(CONF_DAYS_BACK, DEFAULT_DAYS_BACK),
        ): vol.All(
            vol.Coerce(int),
            vol.Range(min=MIN_DAYS_BACK, max=MAX_DAYS_BACK),
        ),
    }
