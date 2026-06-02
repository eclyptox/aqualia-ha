"""Sensor platform for Aqualia."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfVolume
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import _parse_datetime
from .const import DOMAIN
from .coordinator import AqualiaDataUpdateCoordinator


@dataclass(frozen=True)
class AqualiaSensorDescription:
    """Describes an Aqualia sensor."""

    key: str
    name: str
    native_unit_of_measurement: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    icon: str | None = None
    value_fn: Callable[[Any], Any] | None = None


SENSORS: tuple[AqualiaSensorDescription, ...] = (
    AqualiaSensorDescription(
        key="last_value",
        name="Last Reading",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water",
        value_fn=lambda value: round(value, 0) if value is not None else None,
    ),
    AqualiaSensorDescription(
        key="daily_normalized",
        name="Daily Normalized Consumption",
        native_unit_of_measurement="L/d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda value: round(value, 2) if value is not None else None,
    ),
    AqualiaSensorDescription(
        key="avg_daily_30d",
        name="30 Day Average",
        native_unit_of_measurement="L/d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        value_fn=lambda value: round(value, 2) if value is not None else None,
    ),
    AqualiaSensorDescription(
        key="ratio_vs_avg",
        name="Ratio vs 30 Day Average",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
        value_fn=lambda value: round(value, 1) if value is not None else None,
    ),
    AqualiaSensorDescription(
        key="monthly_total",
        name="Monthly Total",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:water",
        value_fn=lambda value: round(value, 0) if value is not None else None,
    ),
    AqualiaSensorDescription(
        key="days_since_reading",
        name="Days Since Last Reading",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
    ),
    AqualiaSensorDescription(
        key="reading_gap_days",
        name="Reading Gap",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-range",
    ),
    AqualiaSensorDescription(
        key="last_reading_date",
        name="Last Reading Date",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-check",
    ),
)

_DEVICE_INFO_KEYS = {"identifiers", "manufacturer", "name"}


def _device_info(entry: ConfigEntry) -> dict:
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "manufacturer": "Aqualia",
        "name": "Aqualia Water Meter",
    }


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Aqualia sensors."""

    coordinator: AqualiaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        AqualiaSensor(coordinator, entry, description) for description in SENSORS
    ]
    entities.append(AqualiaCumulativeSensor(coordinator, entry))
    async_add_entities(entities)


class AqualiaSensor(
    CoordinatorEntity[AqualiaDataUpdateCoordinator], SensorEntity
):
    """Aqualia metric sensor."""

    entity_description: AqualiaSensorDescription

    def __init__(
        self,
        coordinator: AqualiaDataUpdateCoordinator,
        entry: ConfigEntry,
        description: AqualiaSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_has_entity_name = True
        self._attr_name = description.name
        self._attr_device_info = _device_info(entry)

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self.entity_description.native_unit_of_measurement

    @property
    def state_class(self) -> SensorStateClass | None:
        return self.entity_description.state_class

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return self.entity_description.device_class

    @property
    def icon(self) -> str | None:
        return self.entity_description.icon

    @property
    def native_value(self) -> Any:
        value = self.coordinator.data.get(self.entity_description.key)
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value


class AqualiaCumulativeSensor(
    CoordinatorEntity[AqualiaDataUpdateCoordinator], RestoreEntity, SensorEntity
):
    """Cumulative water consumption sensor for the Energy Dashboard.

    Accumulates all interval readings from the Aqualia API into a monotonically
    increasing total. State is persisted across HA restarts via RestoreEntity so
    readings already counted are never double-counted.
    """

    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water-plus"
    _attr_has_entity_name = True
    _attr_name = "Total Consumption"
    _attr_translation_key = "total_consumption"

    def __init__(
        self,
        coordinator: AqualiaDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_total_consumption"
        self._attr_device_info = _device_info(entry)
        self._total: float = 0.0
        self._last_processed_date: datetime | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            try:
                self._total = float(last_state.state)
            except (ValueError, TypeError):
                self._total = 0.0
            if raw_date := last_state.attributes.get("last_processed_date"):
                try:
                    self._last_processed_date = datetime.fromisoformat(raw_date)
                except (ValueError, TypeError):
                    pass
        self._process_readings()

    def _process_readings(self) -> None:
        data = self.coordinator.data
        if not data:
            return
        for reading in sorted(
            data.get("readings", []),
            key=lambda r: _parse_datetime(r.get("Date")),
        ):
            date = _parse_datetime(reading.get("Date"))
            if self._last_processed_date is None or date > self._last_processed_date:
                self._total += float(reading.get("Value", 0))
                self._last_processed_date = date

    @callback
    def _handle_coordinator_update(self) -> None:
        self._process_readings()
        self.async_write_ha_state()

    @property
    def native_value(self) -> float:
        return round(self._total, 0)

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        return {
            "last_processed_date": (
                self._last_processed_date.isoformat()
                if self._last_processed_date
                else None
            )
        }
