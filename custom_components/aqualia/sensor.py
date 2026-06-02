"""Sensor platform for Aqualia."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Aqualia sensors."""

    coordinator: AqualiaDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AqualiaSensor(coordinator, entry, description) for description in SENSORS
    )


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
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": "Aqualia",
            "name": "Aqualia Water Meter",
        }

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
