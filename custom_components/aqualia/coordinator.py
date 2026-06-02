"""Data coordinator for Aqualia."""

from __future__ import annotations

from datetime import timedelta
from functools import partial
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AqualiaApiError, AqualiaAuthError, AqualiaClient
from .const import (
    CONF_CAC_CODE,
    CONF_CONTRACT_CODE,
    CONF_CONTRACT_NUMBER,
    CONF_DAYS_BACK,
    CONF_INSTALLATION_CODE,
    CONF_POLL_INTERVAL_MINUTES,
    DEFAULT_DAYS_BACK,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class AqualiaDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch Aqualia metrics at a configured interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: AqualiaClient,
    ) -> None:
        self.entry = entry
        self.client = client
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                minutes=entry.data.get(
                    CONF_POLL_INTERVAL_MINUTES,
                    int(DEFAULT_UPDATE_INTERVAL.total_seconds() / 60),
                )
            ),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        data = self.entry.data
        try:
            return await self.hass.async_add_executor_job(
                partial(
                    self.client.fetch_metrics,
                    days_back=data.get(CONF_DAYS_BACK, DEFAULT_DAYS_BACK),
                    cac_code=data[CONF_CAC_CODE],
                    contract_code=data[CONF_CONTRACT_CODE],
                    installation_code=data[CONF_INSTALLATION_CODE],
                    contract_number=data[CONF_CONTRACT_NUMBER],
                )
            )
        except AqualiaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AqualiaApiError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Error actualizando Aqualia: {err}") from err
