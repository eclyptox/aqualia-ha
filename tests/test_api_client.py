"""Tests for AqualiaClient (HTTP interactions mocked)."""

import base64
from datetime import UTC, datetime, timedelta
import json as jsonlib
import os
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import pytest
import requests

from aqualia import api as api_module
from aqualia.api import (
    AqualiaApiError,
    AqualiaAuthError,
    AqualiaClient,
    AqualiaRateLimitError,
)


@pytest.fixture(autouse=True)
def _reset_login_cooldown():
    api_module._LOGIN_COOLDOWN_UNTIL.clear()
    yield
    api_module._LOGIN_COOLDOWN_UNTIL.clear()


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


_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_OAEP = padding.OAEP(
    mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None
)


def _rsa_decrypt(value_b64: str) -> bytes:
    return _PRIVATE_KEY.decrypt(base64.b64decode(value_b64), _OAEP)


def _login_client(password: str = "pass") -> AqualiaClient:
    client = AqualiaClient("12345678A", password)
    client._public_key = _PRIVATE_KEY.public_key()
    return client


def _encrypted_login_response(payload: dict, status_code: int = 200):
    """Build a side_effect that answers like Aqualia: AES-GCM with the session key."""

    def _post(url, json=None, **kwargs):
        aes_key = _rsa_decrypt(json["SessionKey"])
        iv = os.urandom(12)
        blob = iv + AESGCM(aes_key).encrypt(iv, jsonlib.dumps(payload).encode(), None)
        return _make_response(
            status_code, {"Payload": base64.b64encode(blob).decode()}
        )

    return _post


class TestLogin:
    def test_successful_login_stores_token(self):
        client = _login_client()
        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = _encrypted_login_response(
                {"ResponseCode": "00001", "Token": "jwt-abc"}
            )
            client._login()
        assert client.token == "jwt-abc"
        assert client.token_expires_at is not None

    def test_credentials_are_sent_rsa_encrypted(self):
        client = _login_client("s3cret")
        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = _encrypted_login_response({"Token": "tok"})
            client._login()
        body = mock_post.call_args.kwargs["json"]
        assert body["LoginType"] == 1
        assert _rsa_decrypt(body["User"]) == b"12345678A"
        assert _rsa_decrypt(body["Password"]) == b"s3cret"
        assert len(_rsa_decrypt(body["SessionKey"])) == 32

    def test_401_raises_auth_error(self):
        client = _login_client("bad")
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(401)
            with pytest.raises(AqualiaAuthError):
                client._login()

    def test_403_raises_auth_error(self):
        client = _login_client("bad")
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(403)
            with pytest.raises(AqualiaAuthError):
                client._login()

    def test_invalid_credentials_response_code_raises_auth_error(self):
        client = _login_client("bad")
        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = _encrypted_login_response(
                {"ResponseCode": "99980", "ResponseDescription": "Ok"}
            )
            with pytest.raises(AqualiaAuthError):
                client._login()

    def test_unknown_response_code_without_token_raises_api_error(self):
        client = _login_client()
        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = _encrypted_login_response({"ResponseCode": "99999"})
            with pytest.raises(AqualiaApiError) as exc:
                client._login()
        assert not isinstance(exc.value, AqualiaAuthError)
        assert "99999" in str(exc.value)

    def test_unencrypted_response_without_payload_raises_api_error(self):
        client = _login_client()
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(200, {"OtherField": "value"})
            with pytest.raises(AqualiaApiError):
                client._login()

    def test_429_raises_rate_limit_error(self):
        client = _login_client()
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(429)
            with pytest.raises(AqualiaRateLimitError):
                client._login()

    def test_token_expiry_set_to_8_hours(self):
        client = _login_client()
        before = datetime.now(UTC)
        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = _encrypted_login_response({"Token": "tok"})
            client._login()
        delta = client.token_expires_at - before
        assert timedelta(hours=7, minutes=59) < delta <= timedelta(hours=8, seconds=5)

    def test_shorter_server_expiration_wins(self):
        client = _login_client()
        expires = datetime.now(UTC) + timedelta(hours=1)
        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = _encrypted_login_response(
                {"Token": "tok", "TokenExpirationDate": expires.isoformat()}
            )
            client._login()
        assert abs(client.token_expires_at - expires) < timedelta(seconds=1)

    def test_public_key_fetched_from_web_config_and_cached(self):
        client = AqualiaClient("12345678A", "pass")
        pem = _PRIVATE_KEY.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        config = {"pkEnc": base64.b64encode(pem).decode()}
        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value = _make_response(200, config)
            first = client._get_public_key()
            second = client._get_public_key()
        assert first is second
        mock_get.assert_called_once()
        assert mock_get.call_args.args[0] == AqualiaClient.WEB_CONFIG_URL

    def test_missing_public_key_raises_api_error(self):
        client = AqualiaClient("12345678A", "pass")
        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value = _make_response(200, {"BASEURL": "x"})
            with pytest.raises(AqualiaApiError):
                client._get_public_key()


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

    def test_rate_limit_not_retried(self):
        # Retrying a 429 is what kept the IP blocked: every HA setup retry fired
        # three more logins.  Give up at once and let HA's own backoff space it.
        client = AqualiaClient("12345678A", "pass")
        with patch.object(
            client, "_login", side_effect=AqualiaRateLimitError("429")
        ) as mock_login:
            with patch("time.sleep") as mock_sleep:
                with pytest.raises(AqualiaRateLimitError):
                    client._ensure_token()
        assert mock_login.call_count == 1
        mock_sleep.assert_not_called()

    def test_429_starts_cooldown_shared_across_clients(self):
        # HA builds a new client on every setup retry, so the cooldown must
        # outlive the client instance or each retry would hit Aqualia again.
        first = _login_client()
        with patch.object(first.session, "post") as mock_post:
            mock_post.return_value = _make_response(429)
            with pytest.raises(AqualiaRateLimitError):
                first._ensure_token()

        second = _login_client()
        with patch.object(second.session, "post") as mock_post:
            with pytest.raises(AqualiaRateLimitError):
                second._ensure_token()
            mock_post.assert_not_called()

    def test_cooldown_is_per_account(self):
        blocked = _login_client()
        with patch.object(blocked.session, "post") as mock_post:
            mock_post.return_value = _make_response(429)
            with pytest.raises(AqualiaRateLimitError):
                blocked._ensure_token()

        other = AqualiaClient("87654321B", "pass")
        other._public_key = _PRIVATE_KEY.public_key()
        with patch.object(other.session, "post") as mock_post:
            mock_post.side_effect = _encrypted_login_response({"Token": "tok"})
            other._ensure_token()
        assert other.token == "tok"

    def test_login_allowed_again_after_cooldown(self):
        client = _login_client()
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(429)
            with pytest.raises(AqualiaRateLimitError):
                client._ensure_token()

        api_module._LOGIN_COOLDOWN_UNTIL[client.nif] = datetime.now(UTC) - timedelta(
            seconds=1
        )
        with patch.object(client.session, "post") as mock_post:
            mock_post.side_effect = _encrypted_login_response({"Token": "tok"})
            client._ensure_token()
        assert client.token == "tok"

    def test_retry_after_header_sets_cooldown(self):
        client = _login_client()
        resp = _make_response(429)
        resp.headers = {"Retry-After": "120"}
        before = datetime.now(UTC)
        with patch.object(client.session, "post", return_value=resp):
            with pytest.raises(AqualiaRateLimitError):
                client._ensure_token()
        until = api_module._LOGIN_COOLDOWN_UNTIL[client.nif]
        assert timedelta(seconds=119) < until - before < timedelta(seconds=125)

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

    def test_returns_additional_contract_identifier_fields(self):
        client = self._client_with_token()
        api_resp = {
            "ContractDetails": [
                {
                    "ContractInfo": {
                        "CacCode": 111,
                        "ContractCode": 222,
                        "InstallationCode": 333,
                        "ContractNumber": "333-1/1-000001",
                        "MunicipalityCode": "3063000100",
                        "EntryDate": "21/12/2005 9:58:36",
                        "ContractStatusCode": 3,
                        "ContractStatus": "Alta definitiva",
                    },
                    "SupplyAddress": "Calle Falsa 123",
                }
            ]
        }
        with patch.object(client.session, "get") as mock_get:
            mock_get.return_value = _make_response(200, api_resp)
            result = client.get_contracts()
        assert result[0]["MunicipalityCode"] == "3063000100"
        assert result[0]["EntryDate"] == "21/12/2005 9:58:36"
        assert result[0]["ContractStatusCode"] == 3
        assert result[0]["ContractStatus"] == "Alta definitiva"


def _invoice_kwargs() -> dict:
    return dict(
        start_date=datetime(2025, 1, 1, tzinfo=UTC),
        end_date=datetime(2026, 6, 1, tzinfo=UTC),
        cac_code=100,
        contract_code=200,
        installation_code=300,
        contract_number="300-1/1-000001",
    )


class TestGetInvoices:
    def _client_with_token(self) -> AqualiaClient:
        c = AqualiaClient("12345678A", "pass")
        c.token = "tok"
        c.token_expires_at = datetime.now(UTC) + timedelta(hours=4)
        return c

    def test_returns_payment_documents(self):
        client = self._client_with_token()
        docs = [{"TotalAmount": 52.77, "Period": "Mar-Abr / 2026", "Status": "Pagado"}]
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(200, {"PaymentDocuments": docs})
            result = client.get_invoices(**_invoice_kwargs())
        assert result == docs

    def test_returns_empty_list_when_no_documents(self):
        client = self._client_with_token()
        with patch.object(client.session, "post") as mock_post:
            mock_post.return_value = _make_response(200, {"PaymentDocuments": []})
            result = client.get_invoices(**_invoice_kwargs())
        assert result == []

    def test_401_forces_relogin_and_retries(self):
        client = self._client_with_token()
        docs = [{"TotalAmount": 52.77}]
        responses = [
            _make_response(401),
            _make_response(200, {"PaymentDocuments": docs}),
        ]
        with patch.object(client.session, "post", side_effect=responses):
            with patch.object(client, "_login"):
                result = client.get_invoices(**_invoice_kwargs())
        assert result == docs

    def test_401_twice_raises_auth_error(self):
        client = self._client_with_token()
        with patch.object(client.session, "post", return_value=_make_response(401)):
            with patch.object(client, "_login"):
                with pytest.raises(AqualiaAuthError):
                    client.get_invoices(**_invoice_kwargs())

    def test_403_raises_auth_error_immediately(self):
        client = self._client_with_token()
        with patch.object(client.session, "post", return_value=_make_response(403)):
            with pytest.raises(AqualiaAuthError):
                client.get_invoices(**_invoice_kwargs())

    def test_sends_full_contract_identifier(self):
        client = self._client_with_token()
        captured = {}
        def mock_post(url, json=None, **kwargs):
            captured.update(json or {})
            return _make_response(200, {"PaymentDocuments": []})
        with patch.object(client.session, "post", side_effect=mock_post):
            client.get_invoices(
                **_invoice_kwargs(),
                municipality_code="3063000100",
                entry_date="21/12/2005 9:58:36",
                contract_status_code=3,
                contract_status="Alta definitiva",
            )
        ident = captured["ContractIdentifier"]
        assert ident["MunicipalityCode"] == "3063000100"
        assert ident["EntryDate"] == "21/12/2005 9:58:36"
        assert ident["ContractStatusCode"] == 3
        assert ident["ContractStatus"] == "Alta definitiva"
        assert captured.get("HasDebt") is None
