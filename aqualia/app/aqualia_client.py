import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import requests

from token_cache import TokenCache

logger = logging.getLogger(__name__)


class AqualiaClient:
    """Cliente de la API de Aqualia con manejo de autenticación."""

    BASE_URL = "https://oficinavirtualapi.aqualia.es/ofcvirtual"
    LOGIN_URL = f"{BASE_URL}/auth/v1/api/auth/Auth/Login"
    CONSUMPTION_URL = f"{BASE_URL}/meter/v1/api/meter/Meter/GetContractConsumptionCurve"

    def __init__(self, nif: str, password: str):
        self.nif = nif
        self.password = password
        self.token_cache = TokenCache()
        self.session = requests.Session()
        self.xsrf_token: Optional[str] = None

    def _get_common_headers(self) -> Dict[str, str]:
        """Retorna headers comunes para todas las requests."""
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

    def _fetch_xsrf_token(self) -> bool:
        """Obtiene el XSRF-TOKEN desde la página de login."""
        try:
            headers = self._get_common_headers()
            response = self.session.get(
                "https://oficinavirtual.aqualia.es/",
                headers=headers,
                timeout=10
            )
            response.raise_for_status()

            # Extraer XSRF-TOKEN de las cookies
            if "XSRF-TOKEN" in self.session.cookies:
                self.xsrf_token = self.session.cookies.get("XSRF-TOKEN")
                logger.info("XSRF-TOKEN obtenido")
                return True
            else:
                logger.error("No se encontró XSRF-TOKEN en la respuesta")
                return False
        except Exception as e:
            logger.error(f"Error obteniendo XSRF-TOKEN: {e}")
            return False

    def _login_with_retries(self, max_retries: int = 3) -> bool:
        """Realiza login con reintentos exponenciales."""
        backoff_times = [5, 15, 60]

        for attempt in range(max_retries):
            try:
                if not self._fetch_xsrf_token():
                    raise Exception("No se pudo obtener XSRF-TOKEN")

                headers = self._get_common_headers()
                if self.xsrf_token:
                    headers["X-XSRF-TOKEN"] = self.xsrf_token

                body = {
                    "LoginType": 1,
                    "User": self.nif,
                    "Password": self.password
                }

                response = self.session.post(
                    self.LOGIN_URL,
                    json=body,
                    headers=headers,
                    timeout=10
                )
                response.raise_for_status()

                data = response.json()
                token = data.get("Token")
                if token:
                    self.token_cache.save(token)
                    logger.info("Login exitoso")
                    return True
                else:
                    logger.error("No se recibió Token en respuesta de login")
                    return False

            except Exception as e:
                logger.warning(f"Intento {attempt + 1}/{max_retries} fallido: {e}")
                if attempt < max_retries - 1:
                    wait_time = backoff_times[attempt]
                    logger.info(f"Esperando {wait_time}s antes de reintentar...")
                    time.sleep(wait_time)

        logger.error("Login falló después de reintentos")
        return False

    def _ensure_token(self) -> bool:
        """Asegura que hay un token válido, renovando si es necesario."""
        cached_token = self.token_cache.get()
        if cached_token:
            return True

        logger.info("Token no disponible o expirado, realizando login...")
        return self._login_with_retries()

    def get_consumption(
        self,
        date_from: datetime,
        date_to: datetime,
        cac_code: int,
        contract_code: int,
        installation_code: int,
        contract_number: str
    ) -> Optional[List[Dict[str, Any]]]:
        """Obtiene el histórico de consumo entre dos fechas."""

        if not self._ensure_token():
            logger.error("No se pudo obtener token válido")
            return None

        token = self.token_cache.get()
        if not token:
            logger.error("Token no disponible")
            return None

        try:
            headers = self._get_common_headers()
            headers["Authorization"] = f"Bearer {token}"

            body = {
                "DateFrom": date_from.isoformat() + "Z" if not date_from.isoformat().endswith("Z") else date_from.isoformat(),
                "DateTo": date_to.isoformat() + "Z" if not date_to.isoformat().endswith("Z") else date_to.isoformat(),
                "Contract": {
                    "CacCode": cac_code,
                    "ContractCode": contract_code,
                    "InstallationCode": installation_code,
                    "ContractNumber": contract_number
                }
            }

            response = self.session.post(
                self.CONSUMPTION_URL,
                json=body,
                headers=headers,
                timeout=10
            )

            if response.status_code == 401:
                logger.warning("Token expirado (401), limpiando caché...")
                self.token_cache.clear()
                return None

            response.raise_for_status()

            data = response.json()
            readings = data if isinstance(data, list) else data.get("Data", [])
            logger.info(f"Obtenidas {len(readings)} lecturas")
            return readings

        except Exception as e:
            logger.error(f"Error obteniendo consumo: {e}")
            return None

    def close(self) -> None:
        """Cierra la sesión."""
        self.session.close()
