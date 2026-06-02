import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class TokenCache:
    """Gestiona el caché del JWT con refresco automático."""

    def __init__(self, cache_path: str = "/share/aqualia_token_cache.json"):
        self.cache_path = cache_path
        self.token: Optional[str] = None
        self.expires_at: Optional[datetime] = None
        self._load_cache()

    def _load_cache(self) -> None:
        """Carga el token del caché si existe y es válido."""
        try:
            if os.path.exists(self.cache_path):
                with open(self.cache_path, 'r') as f:
                    data = json.load(f)
                    self.token = data.get("token")
                    expires_str = data.get("expires_at")
                    if expires_str:
                        self.expires_at = datetime.fromisoformat(expires_str)

                    if self.is_valid():
                        logger.info("Token cargado del caché")
                    else:
                        logger.info("Token en caché expirado")
                        self.token = None
                        self.expires_at = None
        except Exception as e:
            logger.warning(f"Error cargando caché: {e}")

    def save(self, token: str, expires_in_hours: float = 8) -> None:
        """Guarda el token en caché con su fecha de expiración."""
        self.token = token
        self.expires_at = datetime.now() + timedelta(hours=expires_in_hours)

        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, 'w') as f:
                json.dump({
                    "token": self.token,
                    "expires_at": self.expires_at.isoformat()
                }, f)
            logger.info(f"Token guardado en caché, expira en {expires_in_hours}h")
        except Exception as e:
            logger.error(f"Error guardando caché: {e}")

    def is_valid(self) -> bool:
        """Comprueba si el token es válido (no expirado)."""
        if not self.token or not self.expires_at:
            return False
        # Añadir margen de 5 minutos antes de la expiración
        return datetime.now() < (self.expires_at - timedelta(minutes=5))

    def get(self) -> Optional[str]:
        """Obtiene el token si es válido, None si no."""
        if self.is_valid():
            return self.token
        return None

    def clear(self) -> None:
        """Limpia el caché."""
        self.token = None
        self.expires_at = None
        try:
            if os.path.exists(self.cache_path):
                os.remove(self.cache_path)
            logger.info("Caché limpiado")
        except Exception as e:
            logger.error(f"Error limpiando caché: {e}")
