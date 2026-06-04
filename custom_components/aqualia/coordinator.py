"""Data coordinator for Aqualia."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import partial
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AqualiaApiError, AqualiaAuthError, AqualiaClient, InvoiceParser
from .const import (
    CONF_CAC_CODE,
    CONF_CONTRACT_CODE,
    CONF_CONTRACT_NUMBER,
    CONF_CONTRACT_STATUS,
    CONF_CONTRACT_STATUS_CODE,
    CONF_DAYS_BACK,
    CONF_ENTRY_DATE,
    CONF_INSTALLATION_CODE,
    CONF_MUNICIPALITY_CODE,
    CONF_POLL_INTERVAL_MINUTES,
    DEFAULT_DAYS_BACK,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    INVOICE_FETCH_INTERVAL,
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
        self.last_error: str | None = None
        self.last_success_time: datetime | None = None
        self._cached_invoice_data: dict[str, Any] = {}
        self._last_invoice_fetch: datetime | None = None
        self._last_known_invoice_period: str | None = None
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
            consumption = await self.hass.async_add_executor_job(
                partial(
                    self.client.fetch_metrics,
                    days_back=data.get(CONF_DAYS_BACK, DEFAULT_DAYS_BACK),
                    cac_code=data[CONF_CAC_CODE],
                    contract_code=data[CONF_CONTRACT_CODE],
                    installation_code=data[CONF_INSTALLATION_CODE],
                    contract_number=data[CONF_CONTRACT_NUMBER],
                )
            )
            self.last_error = None
            self.last_success_time = datetime.now(UTC)
        except AqualiaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AqualiaApiError as err:
            self.last_error = str(err)
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            self.last_error = str(err)
            raise UpdateFailed(f"Error actualizando Aqualia: {err}") from err

        if self._should_fetch_invoices():
            await self._refresh_invoice_cache(consumption.get("avg_daily_30d"))

        return {**consumption, **self._cached_invoice_data}

    def _should_fetch_invoices(self) -> bool:
        if self._last_invoice_fetch is None:
            return True
        return datetime.now(UTC) - self._last_invoice_fetch > INVOICE_FETCH_INTERVAL

    async def _refresh_invoice_cache(self, avg_daily_30d: float | None) -> None:
        data = self.entry.data
        end = datetime.now(UTC)
        start = end - timedelta(days=730)

        municipality_code = data.get(CONF_MUNICIPALITY_CODE, "")
        entry_date = data.get(CONF_ENTRY_DATE, "")
        contract_status_code = data.get(CONF_CONTRACT_STATUS_CODE, 0)
        contract_status = data.get(CONF_CONTRACT_STATUS, "")

        # Old config entries (installed before this field was captured) lack the
        # full ContractIdentifier.  Resolve it on-the-fly from GetUserLinkedContracts
        # so existing users don't need to delete and re-add the integration.
        if not municipality_code:
            municipality_code, entry_date, contract_status_code, contract_status = (
                await self._resolve_contract_identifier()
            )

        try:
            documents = await self.hass.async_add_executor_job(
                partial(
                    self.client.get_invoices,
                    start_date=start,
                    end_date=end,
                    cac_code=data[CONF_CAC_CODE],
                    contract_code=data[CONF_CONTRACT_CODE],
                    installation_code=data[CONF_INSTALLATION_CODE],
                    contract_number=data[CONF_CONTRACT_NUMBER],
                    municipality_code=municipality_code,
                    entry_date=entry_date,
                    contract_status_code=contract_status_code,
                    contract_status=contract_status,
                )
            )
            parsed = InvoiceParser(documents, avg_daily_30d).parse()
            new_period = parsed.get("latest_invoice_period")
            if (
                self._last_known_invoice_period is not None
                and new_period is not None
                and new_period != self._last_known_invoice_period
            ):
                await self._notify_new_invoice(parsed, new_period)
            if new_period is not None:
                self._last_known_invoice_period = new_period
            self._cached_invoice_data = parsed
            self._last_invoice_fetch = datetime.now(UTC)
        except Exception as err:
            _LOGGER.warning("Aqualia invoice fetch failed, using cached data: %s", err)

    async def _notify_new_invoice(self, invoice_data: dict[str, Any], period: str) -> None:
        """Fire an HA event and create a persistent notification for a new invoice."""
        amount = invoice_data.get("latest_invoice_amount")
        due_date = invoice_data.get("latest_invoice_due_date")

        event_payload: dict[str, Any] = {"period": period}
        if amount is not None:
            event_payload["amount"] = amount
        if due_date is not None:
            event_payload["due_date"] = due_date.isoformat()

        self.hass.bus.async_fire(f"{DOMAIN}_new_invoice", event_payload)

        lines = [f"Período: **{period}**"]
        if amount is not None:
            lines.append(f"Importe: {amount:.2f} €")
        if due_date is not None:
            lines.append(f"Vencimiento: {due_date.strftime('%d/%m/%Y')}")

        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "message": "\n".join(lines),
                "title": "Aqualia: nueva factura",
                "notification_id": f"{DOMAIN}_new_invoice",
            },
        )
        _LOGGER.info("Nueva factura Aqualia detectada: %s (%.2f €)", period, amount or 0)

    async def _resolve_contract_identifier(self) -> tuple[str, str, int, str]:
        """Fetch ContractIdentifier fields from GetUserLinkedContracts.

        Used when the config entry was created before these fields were captured
        during discovery, so existing users don't need to reconfigure.
        Returns (municipality_code, entry_date, contract_status_code, contract_status).
        """
        target = str(self.entry.data[CONF_CONTRACT_NUMBER])
        try:
            contracts = await self.hass.async_add_executor_job(self.client.get_contracts)
            if contracts:
                match = next(
                    (c for c in contracts if str(c.get("ContractNumber", "")) == target),
                    None,
                )
                if match:
                    return (
                        match.get("MunicipalityCode", ""),
                        match.get("EntryDate", ""),
                        match.get("ContractStatusCode", 0) or 0,
                        match.get("ContractStatus", ""),
                    )
        except Exception as err:
            _LOGGER.debug("Could not resolve ContractIdentifier for invoice fetch: %s", err)
        return ("", "", 0, "")
