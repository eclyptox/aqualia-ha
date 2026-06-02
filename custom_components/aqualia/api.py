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

    def __init__(self, nif: str, password: str) -> None:
        self.nif = nif
        self.password = password
        self.session = requests.Session()
        self.xsrf_token: str | None = None
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

    def _fetch_xsrf_token(self) -> None:
        response = self.session.get(
            "https://oficinavirtual.aqualia.es/",
            headers=self._get_common_headers(),
            timeout=10,
        )
        response.raise_for_status()
        self.xsrf_token = self.session.cookies.get("XSRF-TOKEN")
        if not self.xsrf_token:
            raise AqualiaAuthError("No se encontró XSRF-TOKEN en la respuesta")

    def _login(self) -> None:
        self._fetch_xsrf_token()
        headers = self._get_common_headers()
        headers["X-XSRF-TOKEN"] = self.xsrf_token or ""

        response = self.session.post(
            self.LOGIN_URL,
            json={"LoginType": 1, "User": self.nif, "Password": self.password},
            headers=headers,
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
        return data.get("Data", [])

    def fetch_metrics(
        self,
        *,
        days_back: int,
        cac_code: int,
        contract_code: int,
        installation_code: int,
        contract_number: str,
    ) -> dict[str, Any]:
        """Fetch readings and return parsed metrics."""

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
        return ConsumptionParser(readings).parse()

    def close(self) -> None:
        self.session.close()


class ConsumptionParser:
    """Parse Aqualia readings into Home Assistant sensor metrics."""

    def __init__(self, readings: list[dict[str, Any]]) -> None:
        self.readings = sorted(readings, key=lambda item: _parse_datetime(item.get("Date")))

    def parse(self) -> dict[str, Any]:
        if not self.readings:
            return {
                "last_value": None,
                "last_reading_date": None,
                "reading_gap_days": None,
                "daily_normalized": None,
                "monthly_total": None,
                "avg_daily_30d": None,
                "ratio_vs_avg": None,
                "days_since_reading": None,
            }

        return {
            "last_value": self._last_value(),
            "last_reading_date": self._last_reading_date(),
            "reading_gap_days": self._reading_gap_days(),
            "daily_normalized": self._daily_normalized(),
            "monthly_total": self._monthly_total(),
            "avg_daily_30d": self._avg_daily_30d(),
            "ratio_vs_avg": self._ratio_vs_avg(),
            "days_since_reading": self._days_since_reading(),
        }

    def _last_value(self) -> float:
        return float(self.readings[-1].get("Value", 0))

    def _last_reading_date(self) -> datetime:
        return _parse_datetime(self.readings[-1].get("Date"))

    def _reading_gap_days(self) -> int:
        if len(self.readings) < 2:
            return 1
        gap = (
            _parse_datetime(self.readings[-1].get("Date"))
            - _parse_datetime(self.readings[-2].get("Date"))
        ).days
        return max(1, gap)

    def _daily_normalized(self) -> float:
        return self._last_value() / self._reading_gap_days()

    def _monthly_total(self) -> float:
        now = datetime.now(UTC)
        month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
        total = 0.0
        for reading in self.readings:
            date = _parse_datetime(reading.get("Date"))
            if date >= month_start:
                total += float(reading.get("Value", 0))
        return total

    def _avg_daily_30d(self) -> float:
        thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
        values: list[float] = []
        for index, reading in enumerate(self.readings):
            date = _parse_datetime(reading.get("Date"))
            if date < thirty_days_ago:
                continue
            value = float(reading.get("Value", 0))
            if index > 0:
                previous_date = _parse_datetime(self.readings[index - 1].get("Date"))
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
