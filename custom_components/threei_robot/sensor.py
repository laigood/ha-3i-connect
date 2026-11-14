"""Sensors for 3irobotix robots."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ThreeiDevice, ThreeiHub
from .const import DOMAIN, PROP_BATTERY, PROP_CLEAN_AREA, PROP_CLEAN_TIME, PROP_FAULT, PROP_WIND, PROP_WATER
from .vacuum import ThreeiEntity

# (property, name, device_class, unit, category)
SENSORS = [
    (PROP_BATTERY, "Battery", SensorDeviceClass.BATTERY, PERCENTAGE, None),
    (PROP_CLEAN_AREA, "Clean area", None, UnitOfArea.SQUARE_METERS, None),
    (PROP_CLEAN_TIME, "Clean time", SensorDeviceClass.DURATION, UnitOfTime.MINUTES, None),
    (PROP_WIND, "Suction level", None, None, EntityCategory.DIAGNOSTIC),
    (PROP_WATER, "Water level", None, None, EntityCategory.DIAGNOSTIC),
    (PROP_FAULT, "Fault code", None, None, EntityCategory.DIAGNOSTIC),
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: ThreeiHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(ThreeiSensor(hub, d, *s) for d in hub.devices.values() for s in SENSORS)


class ThreeiSensor(ThreeiEntity, SensorEntity):
    def __init__(self, hub: ThreeiHub, dev: ThreeiDevice, prop, name, device_class, unit, category) -> None:
        super().__init__(hub, dev)
        self._prop = prop
        self._attr_name = name
        self._attr_unique_id = f"{dev.sn}_{prop}"
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_entity_category = category
        if unit is not None:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self.dev.props.get(self._prop)
