"""Minimal Home Assistant stubs so sensor.py can be imported without HA installed."""

from enum import StrEnum
from types import ModuleType
from typing import Generic, TypeVar
import sys

_T = TypeVar("_T")


class SensorDeviceClass(StrEnum):
    WATER = "water"
    TIMESTAMP = "timestamp"


class SensorStateClass(StrEnum):
    MEASUREMENT = "measurement"
    TOTAL = "total"
    TOTAL_INCREASING = "total_increasing"


class SensorEntity:
    _attr_unique_id: str | None = None
    _attr_has_entity_name: bool = False
    _attr_name: str | None = None
    _attr_device_info: dict | None = None
    _attr_native_unit_of_measurement: str | None = None
    _attr_device_class: SensorDeviceClass | None = None
    _attr_state_class: SensorStateClass | None = None
    _attr_icon: str | None = None
    _attr_translation_key: str | None = None


class CoordinatorEntity(Generic[_T]):
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def __class_getitem__(cls, item):
        return cls

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success


class ConfigEntry:
    entry_id: str = ""
    data: dict = {}


class UpdateFailed(Exception):
    pass


class ConfigEntryAuthFailed(Exception):
    pass


PERCENTAGE = "%"


class UnitOfVolume:
    LITERS = "L"


def _install():
    """Install stubs into sys.modules so sensor.py imports succeed."""
    def _mod(name: str) -> ModuleType:
        m = ModuleType(name)
        sys.modules[name] = m
        return m

    sensor_mod = _mod("homeassistant.components.sensor")
    sensor_mod.SensorDeviceClass = SensorDeviceClass
    sensor_mod.SensorEntity = SensorEntity
    sensor_mod.SensorStateClass = SensorStateClass

    class DataUpdateCoordinator(Generic[_T]):
        pass

    coord_mod = _mod("homeassistant.helpers.update_coordinator")
    coord_mod.CoordinatorEntity = CoordinatorEntity
    coord_mod.DataUpdateCoordinator = DataUpdateCoordinator
    coord_mod.UpdateFailed = UpdateFailed

    const_mod = _mod("homeassistant.const")
    const_mod.PERCENTAGE = PERCENTAGE
    const_mod.UnitOfVolume = UnitOfVolume
    const_mod.CONF_PASSWORD = "password"

    cfg_mod = _mod("homeassistant.config_entries")
    cfg_mod.ConfigEntry = ConfigEntry
    cfg_mod.ConfigEntryAuthFailed = ConfigEntryAuthFailed

    exc_mod = _mod("homeassistant.exceptions")
    exc_mod.ConfigEntryAuthFailed = ConfigEntryAuthFailed

    core_mod = _mod("homeassistant.core")
    core_mod.HomeAssistant = object

    entity_platform_mod = _mod("homeassistant.helpers.entity_platform")
    entity_platform_mod.AddEntitiesCallback = object

    for name in ["homeassistant", "homeassistant.helpers"]:
        if name not in sys.modules:
            _mod(name)
