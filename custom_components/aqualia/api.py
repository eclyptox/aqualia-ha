"""Aqualia API client and consumption parsing."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)


class AqualiaApiError(Exception):
    """Base API error."""


class AqualiaAuthError(AqualiaApiError):
    """Authentication failed."""


class AqualiaClient:
    """Small synchronous client for Aqualia's virtual office API."""

    BASE_URL = "https://oficinavirtualapi.aqualia.es/ofcvirtual"
    LOGIN_URL = f"{BASE_URL}/auth/v1/api/auth/Auth/Login"
    CONSUMPTION_URL = (
        f"{BASE_URL}/meter/v1/api/meter/Meter/GetContractConsumptionCurve"
    )
    CONTRACTS_URL = (
        f"{BASE_URL}/contract/v1/api/contract/Contract/GetUserLinkedContracts"
    )
    INVOICES_URL = (
        f"{BASE_URL}/invoice/v1/api/invoice/Invoice/GetList"
    )

    def __init__(self, nif: str, password: str) -> None:
        self.nif = nif
        self.password = password
        self.session = requests.Session()
        self.token: str | None = None
        self.token_expires_at: datetime | None = None

    def _get_common_headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-es",
            "Application-Id": "1",
            "Country": "34",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://oficinavirtual.aqualia.es",
            "Referer": "https://oficinavirtual.aqualia.es/",
        }

    def _login(self) -> None:
        response = self.session.post(
            self.LOGIN_URL,
            json={"LoginType": 1, "User": self.nif, "Password": self.password},
            headers=self._get_common_headers(),
            timeout=10,
        )
        if response.status_code in (401, 403):
            raise AqualiaAuthError("Credenciales de Aqualia inválidas")
        response.raise_for_status()

        token = response.json().get("Token")
        if not token:
            raise AqualiaAuthError("No se recibió Token en el login")

        self.token = token
        self.token_expires_at = datetime.now(UTC) + timedelta(hours=8)
        _LOGGER.debug("Aqualia login completed")

    def _ensure_token(self) -> None:
        if (
            self.token
            and self.token_expires_at
            and datetime.now(UTC) < self.token_expires_at - timedelta(minutes=5)
        ):
            return

        backoff_times = [5, 15, 60]
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                self._login()
                return
            except AqualiaAuthError:
                raise
            except Exception as err:  # noqa: BLE001 - convert library errors.
                last_error = err
                if attempt < 2:
                    time.sleep(backoff_times[attempt])

        raise AqualiaApiError(f"Login falló después de reintentos: {last_error}")

    def get_consumption(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        cac_code: int,
        contract_code: int,
        installation_code: int,
        contract_number: str,
    ) -> list[dict[str, Any]]:
        """Return raw consumption readings for a date range."""

        self._ensure_token()
        readings = self._request_consumption(
            date_from=date_from,
            date_to=date_to,
            cac_code=cac_code,
            contract_code=contract_code,
            installation_code=installation_code,
            contract_number=contract_number,
        )
        if readings is not None:
            return readings

        self.token = None
        self.token_expires_at = None
        self._ensure_token()
        readings = self._request_consumption(
            date_from=date_from,
            date_to=date_to,
            cac_code=cac_code,
            contract_code=contract_code,
            installation_code=installation_code,
            contract_number=contract_number,
        )
        if readings is None:
            raise AqualiaAuthError("Token expirado o rechazado por Aqualia")
        return readings

    def _request_consumption(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        cac_code: int,
        contract_code: int,
        installation_code: int,
        contract_number: str,
    ) -> list[dict[str, Any]] | None:
        headers = self._get_common_headers()
        headers["Authorization"] = f"Bearer {self.token}"
        body = {
            "DateFrom": _format_aqualia_datetime(date_from),
            "DateTo": _format_aqualia_datetime(date_to),
            "Contract": {
                "CacCode": cac_code,
                "ContractCode": contract_code,
                "InstallationCode": installation_code,
                "ContractNumber": contract_number,
            },
        }
        response = self.session.post(
            self.CONSUMPTION_URL,
            json=body,
            headers=headers,
            timeout=10,
        )
        if response.status_code == 401:
            return None
        if response.status_code in (403,):
            raise AqualiaAuthError("Aqualia rechazó la autenticación")
        response.raise_for_status()

        data = response.json()
        if isinstance(data, list):
            return data
        return data.get("ConsumptionCurves") or data.get("Data") or []

    def fetch_metrics(
        self,
        *,
        days_back: int,
        cac_code: int,
        contract_code: int,
        installation_code: int,
        contract_number: str,
    ) -> dict[str, Any]:
        """Fetch readings and return parsed metrics plus the raw readings list."""

        date_to = datetime.now(UTC)
        date_from = date_to - timedelta(days=days_back)
        readings = self.get_consumption(
            date_from=date_from,
            date_to=date_to,
            cac_code=cac_code,
            contract_code=contract_code,
            installation_code=installation_code,
            contract_number=contract_number,
        )
        return {"readings": readings, **ConsumptionParser(readings).parse()}

    def get_contracts(self) -> list[dict[str, Any]] | None:
        """Return contracts for the authenticated user.

        Propagates AqualiaAuthError so callers can surface bad credentials.
        Returns None when the endpoint is unavailable (caller falls back to
        manual entry).
        """
        self._ensure_token()
        headers = self._get_common_headers()
        headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = self.session.get(
                self.CONTRACTS_URL, headers=headers, timeout=10
            )
            if response.status_code in (401, 403, 404, 405):
                return None
            response.raise_for_status()
            data = response.json()
            details = data.get("ContractDetails", [])
            if not isinstance(details, list) or not details:
                return None
            # Flatten: merge ContractInfo fields with the address for display.
            # We capture the full ContractIdentifier so the invoice API works
            # without asking the user to enter these values manually.
            contracts = []
            for item in details:
                info = item.get("ContractInfo", {})
                contracts.append({
                    "CacCode": info.get("CacCode"),
                    "ContractCode": info.get("ContractCode"),
                    "InstallationCode": info.get("InstallationCode"),
                    "ContractNumber": info.get("ContractNumber"),
                    "MunicipalityCode": str(info.get("MunicipalityCode", "")),
                    "EntryDate": str(info.get("EntryDate", "")),
                    "ContractStatusCode": info.get("ContractStatusCode", 0) or 0,
                    "ContractStatus": str(info.get("ContractStatus", "")),
                    "Address": item.get("SupplyAddress", ""),
                })
            return contracts
        except AqualiaAuthError:
            raise
        except Exception:  # noqa: BLE001 - treat all other errors as unavailable
            return None

    def get_invoices(
        self,
        *,
        start_date: datetime,
        end_date: datetime,
        cac_code: int,
        contract_code: int,
        installation_code: int,
        contract_number: str,
        municipality_code: str = "",
        entry_date: str = "",
        contract_status_code: int = 0,
        contract_status: str = "",
    ) -> list[dict[str, Any]]:
        """Return payment documents for the given date range."""
        self._ensure_token()
        documents = self._request_invoices(
            start_date=start_date,
            end_date=end_date,
            cac_code=cac_code,
            contract_code=contract_code,
            installation_code=installation_code,
            contract_number=contract_number,
            municipality_code=municipality_code,
            entry_date=entry_date,
            contract_status_code=contract_status_code,
            contract_status=contract_status,
        )
        if documents is not None:
            return documents

        self.token = None
        self.token_expires_at = None
        self._ensure_token()
        documents = self._request_invoices(
            start_date=start_date,
            end_date=end_date,
            cac_code=cac_code,
            contract_code=contract_code,
            installation_code=installation_code,
            contract_number=contract_number,
            municipality_code=municipality_code,
            entry_date=entry_date,
            contract_status_code=contract_status_code,
            contract_status=contract_status,
        )
        if documents is None:
            raise AqualiaAuthError("Token expirado o rechazado por Aqualia")
        return documents

    def _request_invoices(
        self,
        *,
        start_date: datetime,
        end_date: datetime,
        cac_code: int,
        contract_code: int,
        installation_code: int,
        contract_number: str,
        municipality_code: str,
        entry_date: str,
        contract_status_code: int,
        contract_status: str,
    ) -> list[dict[str, Any]] | None:
        headers = self._get_common_headers()
        headers["Authorization"] = f"Bearer {self.token}"
        body = {
            "StartDate": _format_aqualia_datetime(start_date),
            "EndDate": _format_aqualia_datetime(end_date),
            "ContractIdentifier": {
                "CacCode": cac_code,
                "ContractCode": contract_code,
                "ContractNumber": contract_number,
                "InstallationCode": installation_code,
                "MunicipalityCode": municipality_code,
                "EntryDate": entry_date,
                "ContractStatusCode": contract_status_code,
                "ContractStatus": contract_status,
                "styleClass": "",
            },
            "HasDebt": None,
        }
        response = self.session.post(
            self.INVOICES_URL,
            json=body,
            headers=headers,
            timeout=30,
        )
        if response.status_code == 401:
            return None
        if response.status_code == 403:
            raise AqualiaAuthError("Aqualia rechazó la autenticación")
        response.raise_for_status()
        return response.json().get("PaymentDocuments", [])

    def close(self) -> None:
        self.session.close()


class ConsumptionParser:
    """Parse Aqualia readings into Home Assistant sensor metrics.

    API field names (confirmed from GetContractConsumptionCurve response):
      DateTimeConsumptionCurve  — ISO datetime of the reading
      ConsumptionValue          — litres consumed in this interval
      ReadingIndex              — cumulative meter total (odometer-style)
    """

    _DATE = "DateTimeConsumptionCurve"
    _VALUE = "ConsumptionValue"
    _INDEX = "ReadingIndex"

    def __init__(self, readings: list[dict[str, Any]]) -> None:
        self.readings = sorted(
            readings, key=lambda item: _parse_datetime(item.get(self._DATE))
        )

    def parse(self) -> dict[str, Any]:
        if not self.readings:
            return {
                "last_value": None,
                "reading_index": None,
                "last_reading_date": None,
                "reading_gap_days": None,
                "daily_normalized": None,
                "today_consumption": None,
                "monthly_total": None,
                "avg_daily_30d": None,
                "ratio_vs_avg": None,
                "days_since_reading": None,
            }

        return {
            "last_value": self._last_value(),
            "reading_index": self._reading_index(),
            "last_reading_date": self._last_reading_date(),
            "reading_gap_days": self._reading_gap_days(),
            "daily_normalized": self._daily_normalized(),
            "today_consumption": self._today_consumption(),
            "monthly_total": self._monthly_total(),
            "avg_daily_30d": self._avg_daily_30d(),
            "ratio_vs_avg": self._ratio_vs_avg(),
            "days_since_reading": self._days_since_reading(),
        }

    def _last_value(self) -> float:
        return float(self.readings[-1].get(self._VALUE, 0))

    def _reading_index(self) -> float | None:
        val = self.readings[-1].get(self._INDEX)
        # Return None when missing or zero so the cumulative sensor stays
        # unavailable rather than emitting 0 — a transient 0 from the API
        # would otherwise cause total_increasing to count the full meter
        # value as new consumption when the real reading returns.
        return float(val) if val else None

    def _last_reading_date(self) -> datetime:
        return _parse_datetime(self.readings[-1].get(self._DATE))

    def _reading_gap_days(self) -> int:
        if len(self.readings) < 2:
            return 1
        gap = (
            _parse_datetime(self.readings[-1].get(self._DATE))
            - _parse_datetime(self.readings[-2].get(self._DATE))
        ).days
        return max(1, gap)

    def _daily_normalized(self) -> float:
        return self._last_value() / self._reading_gap_days()

    def _today_consumption(self) -> float:
        today = datetime.now(UTC).date()
        return sum(
            float(r.get(self._VALUE, 0))
            for r in self.readings
            if _parse_datetime(r.get(self._DATE)).date() == today
        )

    def _monthly_total(self) -> float:
        now = datetime.now(UTC)
        month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
        total = 0.0
        for reading in self.readings:
            date = _parse_datetime(reading.get(self._DATE))
            if date >= month_start:
                total += float(reading.get(self._VALUE, 0))
        return total

    def _avg_daily_30d(self) -> float:
        thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
        values: list[float] = []
        for index, reading in enumerate(self.readings):
            date = _parse_datetime(reading.get(self._DATE))
            if date < thirty_days_ago:
                continue
            value = float(reading.get(self._VALUE, 0))
            if index > 0:
                previous_date = _parse_datetime(self.readings[index - 1].get(self._DATE))
                gap = max(1, (date - previous_date).days)
            else:
                gap = 1
            values.append(value / gap)
        return sum(values) / len(values) if values else 0.0

    def _ratio_vs_avg(self) -> float:
        average = self._avg_daily_30d()
        if average <= 0:
            return 0.0
        return (self._daily_normalized() / average) * 100

    def _days_since_reading(self) -> int:
        return max(0, (datetime.now(UTC) - self._last_reading_date()).days)


class InvoiceParser:
    """Parse Aqualia PaymentDocuments into Home Assistant sensor metrics.

    water_price_per_m3 is an *effective* price (fixed charges + variable
    cost) computed by dividing the average invoice amount by the estimated
    water volume consumed during a typical billing period.  It is useful
    as a price sensor for the HA Energy Dashboard, but does not reflect the
    marginal per-m³ tariff shown on the invoice breakdown.
    """

    _TYPICAL_BILLING_DAYS = 61  # Aqualia bills every ~2 months

    def __init__(
        self,
        documents: list[dict[str, Any]],
        avg_daily_liters: float | None = None,
    ) -> None:
        self.documents = sorted(
            documents,
            key=lambda d: d.get("IssueDate", ""),
            reverse=True,
        )
        self.avg_daily_liters = avg_daily_liters

    def parse(self) -> dict[str, Any]:
        if not self.documents:
            return {
                "latest_invoice_amount": None,
                "latest_invoice_period": None,
                "latest_invoice_due_date": None,
                "latest_invoice_status": None,
                "pending_invoice_amount": None,
                "avg_invoice_amount": None,
                "water_price_per_m3": None,
            }

        latest = self.documents[0]
        pending = round(sum(d.get("PendingAmount", 0) for d in self.documents), 2)
        amounts = [d["TotalAmount"] for d in self.documents if d.get("TotalAmount") is not None]
        avg_amount = sum(amounts) / len(amounts) if amounts else None

        raw_due = latest.get("DueDate")
        due_date = _parse_datetime(raw_due) if raw_due else None

        return {
            "latest_invoice_amount": latest.get("TotalAmount"),
            "latest_invoice_period": latest.get("Period"),
            "latest_invoice_due_date": due_date,
            "latest_invoice_status": latest.get("Status"),
            "pending_invoice_amount": pending,
            "avg_invoice_amount": round(avg_amount, 2) if avg_amount is not None else None,
            "water_price_per_m3": self._water_price(avg_amount),
        }

    def _water_price(self, avg_amount: float | None) -> float | None:
        if not avg_amount or not self.avg_daily_liters or self.avg_daily_liters <= 0:
            return None
        billing_days = self._billing_period_days()
        m3 = self.avg_daily_liters * billing_days / 1000
        if m3 <= 0:
            return None
        return round(avg_amount / m3, 4)

    def _billing_period_days(self) -> int:
        """Estimate billing period length from gaps between invoice dates."""
        dates = [
            _parse_datetime(d.get("IssueDate", ""))
            for d in self.documents
            if d.get("IssueDate")
        ]
        if len(dates) < 2:
            return self._TYPICAL_BILLING_DAYS
        gaps = [(dates[i] - dates[i + 1]).days for i in range(len(dates) - 1)]
        return round(sum(gaps) / len(gaps)) or self._TYPICAL_BILLING_DAYS


def _parse_datetime(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _format_aqualia_datetime(value: datetime) -> str:
    value = value.astimezone(UTC)
    return value.isoformat().replace("+00:00", "Z")
