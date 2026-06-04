"""Sensor platform for Aqualia."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
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

# Readings older than this are considered stale → derived sensors go unavailable
_STALE_DAYS = 7


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
    # If True, sensor goes unavailable when data is stale (>_STALE_DAYS days old)
    stale_unavailable: bool = False


SENSORS: tuple[AqualiaSensorDescription, ...] = (
    AqualiaSensorDescription(
        key="last_value",
        name="Last Reading (Aqualia, may be delayed)",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water",
        value_fn=lambda v: round(v, 1) if v is not None else None,
    ),
    AqualiaSensorDescription(
        key="today_consumption",
        name="Consumed Today (Aqualia)",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:water-outline",
        value_fn=lambda v: round(v, 1) if v is not None else None,
        stale_unavailable=True,
    ),
    AqualiaSensorDescription(
        key="monthly_total",
        name="Consumed This Month (Aqualia)",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:water",
        value_fn=lambda v: round(v, 1) if v is not None else None,
        stale_unavailable=True,
    ),
    AqualiaSensorDescription(
        key="daily_normalized",
        name="Estimated Daily Consumption (Aqualia)",
        native_unit_of_measurement="L/d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda v: round(v, 1) if v is not None else None,
        stale_unavailable=True,
    ),
    AqualiaSensorDescription(
        key="avg_daily_30d",
        name="30-Day Average Daily Consumption (Aqualia)",
        native_unit_of_measurement="L/d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        value_fn=lambda v: round(v, 1) if v is not None else None,
    ),
    AqualiaSensorDescription(
        key="ratio_vs_avg",
        name="Consumption vs 30-Day Average (Aqualia)",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
        value_fn=lambda v: round(v, 1) if v is not None else None,
        stale_unavailable=True,
    ),
    AqualiaSensorDescription(
        key="days_since_reading",
        name="Days Since Last Aqualia Reading",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
    ),
    AqualiaSensorDescription(
        key="reading_gap_days",
        name="Last Reading Gap (Aqualia)",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-range",
    ),
    AqualiaSensorDescription(
        key="last_reading_date",
        name="Last Reading Date (Aqualia)",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-check",
    ),
)


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
    def available(self) -> bool:
        if self.coordinator.data is None:
            return False
        if self.entity_description.stale_unavailable:
            last_date = self.coordinator.data.get("last_reading_date")
            if last_date is None:
                return False
            if (datetime.now(UTC) - last_date).days > _STALE_DAYS:
                return False
        return True

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.entity_description.key)
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        days = self.coordinator.data.get("days_since_reading")
        if days is None:
            return {}
        return {"days_since_reading": days}


class AqualiaCumulativeSensor(
    CoordinatorEntity[AqualiaDataUpdateCoordinator], SensorEntity
):
    """Cumulative water consumption sensor for the Energy Dashboard.

    Reflects ReadingIndex from the API — the physical meter odometer value.
    Note: Aqualia readings are typically delayed 2–3 days and may arrive
    batched, so this value lags behind real-time consumption.
    """

    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_device_class = SensorDeviceClass.WATER
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:water-plus"
    _attr_has_entity_name = True
    _attr_name = "Total Consumption (Aqualia meter index)"

    def __init__(
        self,
        coordinator: AqualiaDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_total_consumption"
        self._attr_device_info = _device_info(entry)

    @property
    def available(self) -> bool:
        return self.coordinator.data is not None

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get("reading_index")
        return round(value, 1) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        attrs: dict[str, Any] = {}
        last_date = self.coordinator.data.get("last_reading_date")
        if last_date is not None:
            attrs["last_reading_date"] = last_date.isoformat()
            days_since = (datetime.now(UTC) - last_date).days
            attrs["days_since_reading"] = days_since
            attrs["data_delayed"] = days_since > 0
        if self.coordinator.last_success_time is not None:
            attrs["last_update_success"] = self.coordinator.last_success_time.isoformat()
        if self.coordinator.last_error:
            attrs["api_error"] = self.coordinator.last_error
        return attrs
