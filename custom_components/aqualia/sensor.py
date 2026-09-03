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
    """Describes an Aqualia sensor.

    Mirrors the fields HA reads from entity_description (EntityDescription +
    SensorEntityDescription) so that newer HA versions never hit AttributeError
    when accessing any expected field.  Custom fields come last.
    """

    # ── EntityDescription fields ──────────────────────────────────────────────
    key: str
    name: str | None = None
    icon: str | None = None
    device_class: SensorDeviceClass | None = None
    entity_category: str | None = None
    entity_registry_enabled_default: bool = True
    entity_registry_visible_default: bool = True
    force_update: bool = False
    has_entity_name: bool = False
    translation_key: str | None = None
    translation_placeholders: dict | None = None
    unit_of_measurement: str | None = None

    # ── SensorEntityDescription fields ───────────────────────────────────────
    native_unit_of_measurement: str | None = None
    state_class: SensorStateClass | None = None
    last_reset: datetime | None = None
    options: tuple | None = None
    suggested_display_precision: int | None = None
    suggested_unit_of_measurement: str | None = None

    # ── Custom Aqualia fields ─────────────────────────────────────────────────
    value_fn: Callable[[Any], Any] | None = None
    stale_unavailable: bool = False
    requires_data: bool = False
    extra_attrs_keys: tuple[str, ...] = ()


SENSORS: tuple[AqualiaSensorDescription, ...] = (
    AqualiaSensorDescription(
        key="last_value",
        name="Last reading",
        translation_key="last_value",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water",
        value_fn=lambda v: round(v, 1) if v is not None else None,
    ),
    AqualiaSensorDescription(
        key="today_consumption",
        name="Consumed today",
        translation_key="today_consumption",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:water-outline",
        value_fn=lambda v: round(v, 1) if v is not None else None,
        stale_unavailable=True,
    ),
    AqualiaSensorDescription(
        key="monthly_total",
        name="Consumed this month",
        translation_key="monthly_total",
        native_unit_of_measurement=UnitOfVolume.LITERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:water",
        value_fn=lambda v: round(v, 1) if v is not None else None,
        stale_unavailable=True,
    ),
    AqualiaSensorDescription(
        key="daily_normalized",
        name="Estimated daily consumption",
        translation_key="daily_normalized",
        native_unit_of_measurement="L/d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda v: round(v, 1) if v is not None else None,
        stale_unavailable=True,
    ),
    AqualiaSensorDescription(
        key="avg_daily_30d",
        name="30-day average",
        translation_key="avg_daily_30d",
        native_unit_of_measurement="L/d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:chart-line",
        value_fn=lambda v: round(v, 1) if v is not None else None,
    ),
    AqualiaSensorDescription(
        key="ratio_vs_avg",
        name="Consumption vs 30-day average",
        translation_key="ratio_vs_avg",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:percent",
        value_fn=lambda v: round(v, 1) if v is not None else None,
        stale_unavailable=True,
    ),
    AqualiaSensorDescription(
        key="days_since_reading",
        name="Days since last reading",
        translation_key="days_since_reading",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-clock",
    ),
    AqualiaSensorDescription(
        key="reading_gap_days",
        name="Last reading gap",
        translation_key="reading_gap_days",
        native_unit_of_measurement="d",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:calendar-range",
    ),
    AqualiaSensorDescription(
        key="last_reading_date",
        name="Last reading date",
        translation_key="last_reading_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-check",
    ),
)


INVOICE_SENSORS: tuple[AqualiaSensorDescription, ...] = (
    AqualiaSensorDescription(
        key="latest_invoice_amount",
        name="Latest invoice amount",
        translation_key="latest_invoice_amount",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:receipt",
        value_fn=lambda v: round(v, 2) if v is not None else None,
        requires_data=True,
        extra_attrs_keys=("latest_invoice_period", "latest_invoice_status"),
    ),
    AqualiaSensorDescription(
        key="latest_invoice_due_date",
        name="Latest invoice due date",
        translation_key="latest_invoice_due_date",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        requires_data=True,
    ),
    AqualiaSensorDescription(
        key="pending_invoice_amount",
        name="Pending invoice amount",
        translation_key="pending_invoice_amount",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-clock",
        value_fn=lambda v: round(v, 2) if v is not None else None,
        requires_data=True,
    ),
    AqualiaSensorDescription(
        key="avg_invoice_amount",
        name="Average invoice amount",
        translation_key="avg_invoice_amount",
        native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cash-multiple",
        value_fn=lambda v: round(v, 2) if v is not None else None,
        requires_data=True,
    ),
    AqualiaSensorDescription(
        key="water_price_per_m3",
        name="Estimated water price",
        translation_key="water_price_per_m3",
        native_unit_of_measurement="EUR/m³",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:currency-eur",
        value_fn=lambda v: round(v, 4) if v is not None else None,
        requires_data=True,
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
    entities.extend(
        AqualiaSensor(coordinator, entry, description) for description in INVOICE_SENSORS
    )
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
        # No _attr_name: setting it would override the translated name.  HA
        # resolves translation_key first and falls back to description.name.
        self._attr_translation_key = description.translation_key
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
        if self.entity_description.requires_data:
            if self.coordinator.data.get(self.entity_description.key) is None:
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
        attrs: dict[str, Any] = {}
        # Consumption staleness — only meaningful for non-invoice sensors
        if not self.entity_description.requires_data:
            days = self.coordinator.data.get("days_since_reading")
            if days is not None:
                attrs["days_since_reading"] = days
        # Extra keys declared in the sensor description
        for key in self.entity_description.extra_attrs_keys:
            val = self.coordinator.data.get(key)
            if val is not None:
                attrs[key] = val.isoformat() if hasattr(val, "isoformat") else val
        return attrs


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
    _attr_translation_key = "total_consumption"
    _attr_name = None

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
        # Never emit 0: a transient 0 from the API would be counted as new
        # consumption by total_increasing when the real value returns.
        return round(value, 1) if value else None

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
