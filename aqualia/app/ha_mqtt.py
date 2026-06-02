import json
import logging
from typing import Dict, Any, Optional
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class HAMQTTPublisher:
    """Publica entidades con MQTT Discovery para Home Assistant."""

    DEVICE_ID = "aqualia_water"
    DEVICE_NAME = "Aqualia Water Meter"

    def __init__(
        self,
        host: str,
        port: int,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self._setup_callbacks()
        self.connected = False

    def _setup_callbacks(self) -> None:
        """Configura los callbacks del cliente MQTT."""
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        if rc == 0:
            logger.info("Conectado a MQTT broker")
            self.connected = True
        else:
            logger.error(f"Error conectando a MQTT (código {rc})")
            self.connected = False

    def _on_disconnect(self, client: Any, userdata: Any, rc: int) -> None:
        self.connected = False
        if rc != 0:
            logger.warning(f"Desconexión inesperada (código {rc})")

    def _on_publish(self, client: Any, userdata: Any, mid: Any) -> None:
        pass

    def connect(self) -> bool:
        """Conecta al broker MQTT."""
        try:
            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
            return True
        except Exception as e:
            logger.error(f"Error conectando a MQTT: {e}")
            return False

    def disconnect(self) -> None:
        """Desconecta del broker MQTT."""
        self.client.loop_stop()
        self.client.disconnect()

    def _get_device_info(self) -> Dict[str, Any]:
        """Retorna la info del dispositivo para MQTT Discovery."""
        return {
            "identifiers": [self.DEVICE_ID],
            "name": self.DEVICE_NAME,
            "manufacturer": "Aqualia",
            "model": "Water Meter",
        }

    def _publish_discovery(
        self,
        entity_id: str,
        entity_name: str,
        state_topic: str,
        unit: Optional[str] = None,
        device_class: Optional[str] = None,
        state_class: Optional[str] = None,
        icon: Optional[str] = None,
        entity_category: Optional[str] = None,
    ) -> bool:
        """Publica la configuración de discovery para una entidad."""
        config_topic = f"homeassistant/sensor/aqualia/{entity_id}/config"

        config = {
            "unique_id": f"aqualia_{entity_id}",
            "name": entity_name,
            "state_topic": state_topic,
            "device": self._get_device_info(),
        }

        if unit:
            config["unit_of_measurement"] = unit
        if device_class:
            config["device_class"] = device_class
        if state_class:
            config["state_class"] = state_class
        if icon:
            config["icon"] = icon
        if entity_category:
            config["entity_category"] = entity_category

        try:
            self.client.publish(config_topic, json.dumps(config), retain=True)
            logger.debug(f"Discovery publicado: {config_topic}")
            return True
        except Exception as e:
            logger.error(f"Error publicando discovery {entity_id}: {e}")
            return False

    def publish_metrics(self, metrics: Dict[str, Any]) -> bool:
        """Publica todas las métricas de consumo."""
        try:
            # Última lectura (L)
            self._publish_discovery(
                "last_value",
                "Water Meter - Last Reading",
                "aqualia/sensor/last_value",
                unit="L",
                device_class="water",
                state_class="total_increasing",
                icon="mdi:water"
            )
            self.client.publish(
                "aqualia/sensor/last_value",
                str(metrics.get("last_value", 0)),
                retain=True
            )

            # Consumo normalizado (L/día)
            self._publish_discovery(
                "daily_normalized",
                "Water Meter - Daily Normalized Consumption",
                "aqualia/sensor/daily_normalized",
                unit="L/d",
                device_class="water",
                state_class="measurement",
                icon="mdi:water-percent"
            )
            self.client.publish(
                "aqualia/sensor/daily_normalized",
                f"{metrics.get('daily_normalized', 0):.2f}",
                retain=True
            )

            # Media 30d (L/día)
            self._publish_discovery(
                "avg_30d",
                "Water Meter - 30 Day Average",
                "aqualia/sensor/avg_30d",
                unit="L/d",
                device_class="water",
                state_class="measurement",
                icon="mdi:chart-line"
            )
            self.client.publish(
                "aqualia/sensor/avg_30d",
                f"{metrics.get('avg_daily_30d', 0):.2f}",
                retain=True
            )

            # Ratio vs media (%)
            self._publish_discovery(
                "ratio_vs_avg",
                "Water Meter - Ratio vs 30d Average",
                "aqualia/sensor/ratio_vs_avg",
                unit="%",
                state_class="measurement",
                icon="mdi:percent"
            )
            self.client.publish(
                "aqualia/sensor/ratio_vs_avg",
                f"{metrics.get('ratio_vs_avg', 0):.1f}",
                retain=True
            )

            # Total mensual (L)
            self._publish_discovery(
                "monthly_total",
                "Water Meter - Monthly Total",
                "aqualia/sensor/monthly_total",
                unit="L",
                device_class="water",
                state_class="total",
                icon="mdi:water"
            )
            self.client.publish(
                "aqualia/sensor/monthly_total",
                f"{metrics.get('monthly_total', 0):.0f}",
                retain=True
            )

            # Días sin lectura
            self._publish_discovery(
                "days_since_reading",
                "Water Meter - Days Since Last Reading",
                "aqualia/sensor/days_since_reading",
                unit="d",
                state_class="measurement",
                icon="mdi:calendar-clock"
            )
            self.client.publish(
                "aqualia/sensor/days_since_reading",
                str(metrics.get("days_since_reading", 0)),
                retain=True
            )

            # Gap de lectura (días)
            self._publish_discovery(
                "reading_gap",
                "Water Meter - Reading Gap",
                "aqualia/sensor/reading_gap",
                unit="d",
                state_class="measurement",
                icon="mdi:calendar-range"
            )
            self.client.publish(
                "aqualia/sensor/reading_gap",
                str(metrics.get("reading_gap_days", 0)),
                retain=True
            )

            # Fecha última lectura
            self._publish_discovery(
                "last_reading_date",
                "Water Meter - Last Reading Date",
                "aqualia/sensor/last_reading_date",
                icon="mdi:calendar-check"
            )
            self.client.publish(
                "aqualia/sensor/last_reading_date",
                metrics.get("last_reading_date", ""),
                retain=True
            )

            logger.info("Métricas publicadas en MQTT")
            return True

        except Exception as e:
            logger.error(f"Error publicando métricas: {e}")
            return False

    def publish_error(self) -> None:
        """Publica estado de error en las entidades principales."""
        try:
            self.client.publish("aqualia/sensor/last_value", "unavailable", retain=True)
            self.client.publish("aqualia/sensor/daily_normalized", "unavailable", retain=True)
            logger.info("Estado de error publicado")
        except Exception as e:
            logger.error(f"Error publicando estado de error: {e}")
