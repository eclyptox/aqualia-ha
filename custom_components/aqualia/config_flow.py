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


class AqualiaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Aqualia config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial step."""

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await _validate_input(self.hass, user_input)
            except AqualiaAuthError:
                errors["base"] = "invalid_auth"
            except AqualiaApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - Home Assistant config flow boundary.
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_NIF]}_{user_input[CONF_CONTRACT_NUMBER]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Aqualia {user_input[CONF_CONTRACT_NUMBER]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )


async def _validate_input(hass: HomeAssistant, user_input: dict[str, Any]) -> None:
    client = AqualiaClient(user_input[CONF_NIF], user_input[CONF_PASSWORD])
    try:
        await hass.async_add_executor_job(
            partial(
                client.fetch_metrics,
                days_back=user_input[CONF_DAYS_BACK],
                cac_code=user_input[CONF_CAC_CODE],
                contract_code=user_input[CONF_CONTRACT_CODE],
                installation_code=user_input[CONF_INSTALLATION_CODE],
                contract_number=user_input[CONF_CONTRACT_NUMBER],
            )
        )
    finally:
        await hass.async_add_executor_job(client.close)


def _schema(user_input: dict[str, Any] | None) -> vol.Schema:
    defaults = user_input or {}
    return vol.Schema(
        {
            vol.Required(CONF_NIF, default=defaults.get(CONF_NIF, "")): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(
                CONF_CAC_CODE,
                default=defaults.get(CONF_CAC_CODE, 0),
            ): vol.Coerce(int),
            vol.Required(
                CONF_CONTRACT_CODE,
                default=defaults.get(CONF_CONTRACT_CODE, 0),
            ): vol.Coerce(int),
            vol.Required(
                CONF_INSTALLATION_CODE,
                default=defaults.get(CONF_INSTALLATION_CODE, 0),
            ): vol.Coerce(int),
            vol.Required(
                CONF_CONTRACT_NUMBER,
                default=defaults.get(CONF_CONTRACT_NUMBER, ""),
            ): str,
            vol.Optional(
                CONF_POLL_INTERVAL_MINUTES,
                default=defaults.get(
                    CONF_POLL_INTERVAL_MINUTES, DEFAULT_POLL_INTERVAL_MINUTES
                ),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(
                    min=MIN_POLL_INTERVAL_MINUTES,
                    max=MAX_POLL_INTERVAL_MINUTES,
                ),
            ),
            vol.Optional(
                CONF_DAYS_BACK,
                default=defaults.get(CONF_DAYS_BACK, DEFAULT_DAYS_BACK),
            ): vol.All(
                vol.Coerce(int),
                vol.Range(min=MIN_DAYS_BACK, max=MAX_DAYS_BACK),
            ),
        }
    )
