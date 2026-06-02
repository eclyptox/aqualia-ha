import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ConsumptionParser:
    """Analiza las lecturas de consumo para normalizar y calcular métricas."""

    def __init__(self, readings: List[Dict[str, Any]]):
        self.readings = self._sort_readings(readings)
        self.metrics = {}

    def _sort_readings(self, readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ordena las lecturas por fecha."""
        try:
            return sorted(
                readings,
                key=lambda x: datetime.fromisoformat(
                    x.get("Date", "").replace("Z", "+00:00")
                )
            )
        except Exception as e:
            logger.error(f"Error ordenando lecturas: {e}")
            return readings

    def parse(self) -> Dict[str, Any]:
        """Parsea y calcula todas las métricas."""
        if not self.readings:
            logger.warning("Sin lecturas para procesar")
            return self._empty_metrics()

        self.metrics = {
            "last_value": self._get_last_value(),
            "last_reading_date": self._get_last_reading_date(),
            "reading_gap_days": self._get_reading_gap_days(),
            "daily_normalized": self._get_daily_normalized(),
            "monthly_total": self._get_monthly_total(),
            "avg_daily_30d": self._get_avg_daily_30d(),
            "ratio_vs_avg": self._get_ratio_vs_avg(),
            "days_since_reading": self._get_days_since_reading(),
        }
        return self.metrics

    def _get_last_value(self) -> float:
        """Obtiene el valor de la última lectura."""
        if not self.readings:
            return 0.0
        return float(self.readings[-1].get("Value", 0))

    def _get_last_reading_date(self) -> str:
        """Obtiene la fecha de la última lectura."""
        if not self.readings:
            return ""
        return self.readings[-1].get("Date", "")

    def _get_reading_gap_days(self) -> int:
        """Calcula cuántos días cubre la última lectura."""
        if len(self.readings) < 2:
            return 1

        try:
            last_date = datetime.fromisoformat(
                self.readings[-1].get("Date", "").replace("Z", "+00:00")
            )
            previous_date = datetime.fromisoformat(
                self.readings[-2].get("Date", "").replace("Z", "+00:00")
            )
            gap = (last_date - previous_date).days
            return max(1, gap)
        except Exception as e:
            logger.error(f"Error calculando gap: {e}")
            return 1

    def _get_daily_normalized(self) -> float:
        """Calcula el consumo diario normalizado (corrige lecturas acumuladas)."""
        last_value = self._get_last_value()
        gap = self._get_reading_gap_days()
        if gap > 0:
            return last_value / gap
        return last_value

    def _get_monthly_total(self) -> float:
        """Calcula el consumo total del mes actual."""
        if not self.readings:
            return 0.0

        now = datetime.now()
        month_start = datetime(now.year, now.month, 1)

        total = 0.0
        for reading in self.readings:
            try:
                date = datetime.fromisoformat(
                    reading.get("Date", "").replace("Z", "+00:00")
                )
                if date >= month_start:
                    total += float(reading.get("Value", 0))
            except Exception as e:
                logger.debug(f"Error procesando lectura: {e}")

        return total

    def _get_avg_daily_30d(self) -> float:
        """Calcula la media diaria de los últimos 30 días (sobre valores normalizados)."""
        if not self.readings:
            return 0.0

        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)

        normalized_values = []
        for i, reading in enumerate(self.readings):
            try:
                date = datetime.fromisoformat(
                    reading.get("Date", "").replace("Z", "+00:00")
                )
                if date >= thirty_days_ago:
                    value = float(reading.get("Value", 0))
                    # Calcular gap para esta lectura
                    if i > 0:
                        prev_date = datetime.fromisoformat(
                            self.readings[i - 1].get("Date", "").replace("Z", "+00:00")
                        )
                        gap = max(1, (date - prev_date).days)
                    else:
                        gap = 1
                    normalized = value / gap
                    normalized_values.append(normalized)
            except Exception as e:
                logger.debug(f"Error procesando lectura para media: {e}")

        if normalized_values:
            return sum(normalized_values) / len(normalized_values)
        return 0.0

    def _get_ratio_vs_avg(self) -> float:
        """Calcula el ratio del consumo normalizado vs media 30d (%)."""
        daily_norm = self._get_daily_normalized()
        avg_30d = self._get_avg_daily_30d()

        if avg_30d > 0:
            return (daily_norm / avg_30d) * 100
        return 0.0

    def _get_days_since_reading(self) -> int:
        """Calcula cuántos días han pasado desde la última lectura."""
        last_date_str = self._get_last_reading_date()
        if not last_date_str:
            return 0

        try:
            last_date = datetime.fromisoformat(
                last_date_str.replace("Z", "+00:00")
            ).replace(tzinfo=None)
            now = datetime.now()
            delta = (now - last_date).days
            return max(0, delta)
        except Exception as e:
            logger.error(f"Error calculando días desde lectura: {e}")
            return 0

    def _empty_metrics(self) -> Dict[str, Any]:
        """Retorna un dict de métricas vacías."""
        return {
            "last_value": 0.0,
            "last_reading_date": "",
            "reading_gap_days": 0,
            "daily_normalized": 0.0,
            "monthly_total": 0.0,
            "avg_daily_30d": 0.0,
            "ratio_vs_avg": 0.0,
            "days_since_reading": 0,
        }
