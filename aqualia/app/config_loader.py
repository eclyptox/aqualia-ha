import json
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Carga la configuración del addon desde options.json."""

    def __init__(self):
        self.options_path = "/data/options.json"
        self.config = {}

    def load(self) -> Dict[str, Any]:
        """Carga la configuración desde options.json."""
        try:
            if os.path.exists(self.options_path):
                with open(self.options_path, 'r') as f:
                    self.config = json.load(f)
                logger.info(f"Configuración cargada desde {self.options_path}")
            else:
                logger.warning(f"No se encontró {self.options_path}")
                self.config = {}
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            raise

        return self.config

    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene un valor de configuración."""
        return self.config.get(key, default)

    def validate(self) -> bool:
        """Valida que la configuración tenga los campos requeridos."""
        required = ["nif", "password", "cac_code", "contract_code",
                   "installation_code", "contract_number"]
        for field in required:
            if not self.config.get(field):
                logger.error(f"Falta campo requerido en configuración: {field}")
                return False
        return True

    @property
    def nif(self) -> str:
        return self.get("nif", "")

    @property
    def password(self) -> str:
        return self.get("password", "")

    @property
    def cac_code(self) -> int:
        return self.get("cac_code", 0)

    @property
    def contract_code(self) -> int:
        return self.get("contract_code", 0)

    @property
    def installation_code(self) -> int:
        return self.get("installation_code", 0)

    @property
    def contract_number(self) -> str:
        return self.get("contract_number", "")

    @property
    def poll_interval_minutes(self) -> int:
        return self.get("poll_interval_minutes", 60)

    @property
    def days_back(self) -> int:
        return self.get("days_back", 60)

    @property
    def mqtt_host(self) -> str:
        return self.get("mqtt_host", "core-mosquitto")

    @property
    def mqtt_port(self) -> int:
        return self.get("mqtt_port", 1883)

    @property
    def mqtt_user(self) -> str:
        return self.get("mqtt_user", "")

    @property
    def mqtt_password(self) -> str:
        return self.get("mqtt_password", "")
