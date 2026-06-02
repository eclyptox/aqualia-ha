#!/usr/bin/env python3
import logging
import sys
import time
from datetime import datetime, timedelta

from config_loader import ConfigLoader
from aqualia_client import AqualiaClient
from consumption_parser import ConsumptionParser
from ha_mqtt import HAMQTTPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)


def main():
    """Bucle principal del addon."""
    logger.info("=" * 60)
    logger.info("Aqualia Water Consumption Addon - Iniciando")
    logger.info("=" * 60)

    # Cargar configuración
    config = ConfigLoader()
    if not config.load():
        logger.error("No se pudo cargar la configuración")
        sys.exit(1)

    if not config.validate():
        logger.error("Configuración inválida")
        sys.exit(1)

    logger.info(f"NIF: {config.nif}")
    logger.info(f"Poll interval: {config.poll_interval_minutes} minutos")
    logger.info(f"MQTT: {config.mqtt_host}:{config.mqtt_port}")

    # Crear cliente de API
    aqualia = AqualiaClient(config.nif, config.password)

    # Crear publisher MQTT
    mqtt = HAMQTTPublisher(
        host=config.mqtt_host,
        port=config.mqtt_port,
        username=config.mqtt_user if config.mqtt_user else None,
        password=config.mqtt_password if config.mqtt_password else None
    )

    if not mqtt.connect():
        logger.error("No se pudo conectar a MQTT")
        aqualia.close()
        sys.exit(1)

    # Bandera para publicar inmediatamente
    first_run = True
    last_error_time = None

    # Bucle principal
    while True:
        try:
            now = datetime.now()

            # Publicar inmediatamente en el primer arranque, luego esperar
            if not first_run:
                wait_seconds = config.poll_interval_minutes * 60
                logger.info(f"Esperando {config.poll_interval_minutes} minutos hasta próxima consulta...")
                time.sleep(wait_seconds)

            logger.info("-" * 60)
            logger.info(f"Consultando consumo en {now.isoformat()}")

            # Calcular rango de fechas
            date_to = datetime.now()
            date_from = date_to - timedelta(days=config.days_back)

            logger.info(f"Rango: {date_from.date()} a {date_to.date()}")

            # Obtener consumo
            readings = aqualia.get_consumption(
                date_from=date_from,
                date_to=date_to,
                cac_code=config.cac_code,
                contract_code=config.contract_code,
                installation_code=config.installation_code,
                contract_number=config.contract_number
            )

            if readings is None:
                logger.error("No se pudo obtener consumo")
                mqtt.publish_error()
                last_error_time = datetime.now()
                first_run = False
                continue

            # Procesar lecturas
            parser = ConsumptionParser(readings)
            metrics = parser.parse()

            logger.info(f"Última lectura: {metrics['last_value']:.0f}L")
            logger.info(f"Consumo normalizado: {metrics['daily_normalized']:.2f}L/día")
            logger.info(f"Media 30d: {metrics['avg_daily_30d']:.2f}L/día")
            logger.info(f"Ratio vs media: {metrics['ratio_vs_avg']:.1f}%")
            logger.info(f"Total mensual: {metrics['monthly_total']:.0f}L")
            logger.info(f"Días sin lectura: {metrics['days_since_reading']}")
            logger.info(f"Gap de lectura: {metrics['reading_gap_days']} días")

            # Publicar métricas
            if mqtt.connected:
                mqtt.publish_metrics(metrics)
                last_error_time = None
            else:
                logger.warning("MQTT no conectado, reintentando...")
                mqtt.connect()

            first_run = False

        except KeyboardInterrupt:
            logger.info("Interrupción del usuario, saliendo...")
            break

        except Exception as e:
            logger.exception(f"Error en bucle principal: {e}")
            mqtt.publish_error()
            last_error_time = datetime.now()
            first_run = False

    # Limpieza
    logger.info("Cerrando conexiones...")
    mqtt.disconnect()
    aqualia.close()
    logger.info("Addon terminado")


if __name__ == "__main__":
    main()
