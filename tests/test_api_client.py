"""Tests for AqualiaClient (HTTP interactions mocked)."""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
import requests

from aqualia.api import AqualiaAuthError, AqualiaApiError, AqualiaClient


def _make_response(status_code: int, json_data: Any = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


def _contract_kwargs() -> dict:
    return dict(
        date_from=datetime(2026, 5, 1, tzinfo=UTC),
        date_to=datetime(2026, 5, 15, tzinfo=UTC),
        cac_code=100,
        contract_code=200,
        installation_code=300,
        contract_number="300-1/1-000001",
    )


class TestLogin:
    def test_successful_login_stores_token(self):
        client = AqualiaClient("12345678A", "pass")
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(200, {"Token": "jwt-abc"})
            client._login()
        assert client.token == "jwt-abc"
        assert client.token_expires_at is not None

    def test_401_raises_auth_error(self):
        client = AqualiaClient("12345678A", "bad")
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(401)
            with pytest.raises(AqualiaAuthError):
                client._login()

    def test_403_raises_auth_error(self):
        client = AqualiaClient("12345678A", "bad")
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(403)
            with pytest.raises(AqualiaAuthError):
                client._login()

    def test_missing_token_in_response_raises_auth_error(self):
        client = AqualiaClient("12345678A", "pass")
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(200, {"OtherField": "value"})
            with pytest.raises(AqualiaAuthError):
                client._login()

    def test_token_expiry_set_to_8_hours(self):
        client = AqualiaClient("12345678A", "pass")
        before = datetime.now(UTC)
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(200, {"Token": "tok"})
            client._login()
        after = datetime.now(UTC)
        delta = client.token_expires_at - before
        assert timedelta(hours=7, minutes=59) < delta <= timedelta(hours=8, seconds=5)


class TestEnsureToken:
    def test_skips_login_when_token_valid(self):
        client = AqualiaClient("12345678A", "pass")
        client.token = "valid"
        client.token_expires_at = datetime.now(UTC) + timedelta(hours=4)
        with patch.object(client, "_login") as mock_login:
            client._ensure_token()
            mock_login.assert_not_called()

    def test_logs_in_when_no_token(self):
        client = AqualiaClient("12345678A", "pass")
        with patch.object(client, "_login") as mock_login:
            client._ensure_token()
            mock_login.assert_called_once()

    def test_logs_in_when_token_near_expiry(self):
        client = AqualiaClient("12345678A", "pass")
        client.token = "expiring"
        client.token_expires_at = datetime.now(UTC) + timedelta(minutes=3)
        with patch.object(client, "_login") as mock_login:
            client._ensure_token()
            mock_login.assert_called_once()

    def test_auth_error_not_retried(self):
        client = AqualiaClient("12345678A", "wrong")
        with patch.object(client, "_login", side_effect=AqualiaAuthError("bad creds")):
            with pytest.raises(AqualiaAuthError):
                client._ensure_token()

    def test_network_error_retried_three_times(self):
        client = AqualiaClient("12345678A", "pass")
        with patch.object(client, "_login", side_effect=ConnectionError("timeout")) as mock_login:
            with patch("time.sleep"):
                with pytest.raises(AqualiaApiError):
                    client._ensure_token()
        assert mock_login.call_count == 3


class TestGetConsumption:
    def _client_with_token(self) -> AqualiaClient:
        c = AqualiaClient("12345678A", "pass")
        c.token = "tok"
        c.token_expires_at = datetime.now(UTC) + timedelta(hours=4)
        return c

    def test_returns_list_from_api(self):
        client = self._client_with_token()
        readings = [{"DateTimeConsumptionCurve": "2026-05-01T00:00:00Z",
                     "ConsumptionValue": 100.0, "ReadingIndex": 1000.0}]
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(200, readings)
            result = client.get_consumption(**_contract_kwargs())
        assert result == readings

    def test_unwraps_consumptioncurves_key(self):
        client = self._client_with_token()
        readings = [{"DateTimeConsumptionCurve": "2026-05-01T00:00:00Z",
                     "ConsumptionValue": 90.0, "ReadingIndex": 900.0}]
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(200, {"ConsumptionCurves": readings})
            result = client.get_consumption(**_contract_kwargs())
        assert result == readings

    def test_401_forces_relogin_and_retries(self):
        client = self._client_with_token()
        good_readings = [{"DateTimeConsumptionCurve": "2026-05-01T00:00:00Z",
                          "ConsumptionValue": 80.0, "ReadingIndex": 800.0}]
        responses = [
            _make_response(401),
            _make_response(200, good_readings),
        ]
        with patch.object(client.session, "post", side_effect=responses):
            with patch.object(client, "_login"):
                result = client.get_consumption(**_contract_kwargs())
        assert result == good_readings

    def test_401_twice_raises_auth_error(self):
        client = self._client_with_token()
        with patch.object(client.session, "post", return_value=_make_response(401)):
            with patch.object(client, "_login"):
                with pytest.raises(AqualiaAuthError):
                    client.get_consumption(**_contract_kwargs())

    def test_403_raises_auth_error_immediately(self):
        client = self._client_with_token()
        with patch.object(client.session, "post", return_value=_make_response(403)):
            with pytest.raises(AqualiaAuthError):
                client.get_consumption(**_contract_kwargs())


class TestFetchMetrics:
    def test_returns_metrics_dict(self):
        client = AqualiaClient("12345678A", "pass")
        readings = [{"DateTimeConsumptionCurve": "2026-05-01T00:00:00Z",
                     "ConsumptionValue": 100.0, "ReadingIndex": 1500.0}]
        with patch.object(client, "get_consumption", return_value=readings):
            metrics = client.fetch_metrics(
                days_back=30,
                cac_code=100,
                contract_code=200,
                installation_code=300,
                contract_number="300-1/1-000001",
            )
        assert "last_value" in metrics
        assert "reading_index" in metrics
        assert "daily_normalized" in metrics
        assert "readings" in metrics
        assert metrics["readings"] == readings


class TestGetContracts:
    def _client_with_token(self) -> AqualiaClient:
        c = AqualiaClient("12345678A", "pass")
        c.token = "tok"
        c.token_expires_at = datetime.now(UTC) + timedelta(hours=4)
        return c

    def test_returns_parsed_contracts(self):
        client = self._client_with_token()
        api_resp = {
            "ContractDetails": [
                {
                    "ContractInfo": {
                        "CacCode": 111,
                        "ContractCode": 222,
                        "InstallationCode": 333,
                        "ContractNumber": "333-1/1-000001",
                    },
                    "SupplyAddress": "Calle Falsa 123",
                }
            ]
        }
        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value = _make_response(200, api_resp)
            result = client.get_contracts()
        assert len(result) == 1
        assert result[0]["CacCode"] == 111
        assert result[0]["Address"] == "Calle Falsa 123"

    def test_returns_none_on_404(self):
        client = self._client_with_token()
        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value = _make_response(404)
            result = client.get_contracts()
        assert result is None

    def test_returns_none_on_empty_details(self):
        client = self._client_with_token()
        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value = _make_response(200, {"ContractDetails": []})
            result = client.get_contracts()
        assert result is None

    def test_auth_error_propagates(self):
        client = self._client_with_token()
        with patch.object(client, "_ensure_token", side_effect=AqualiaAuthError("bad")):
            with pytest.raises(AqualiaAuthError):
                client.get_contracts()
