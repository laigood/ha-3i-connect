"""Vacuum entity for 3irobotix robots."""
from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import StateVacuumEntity, VacuumActivity, VacuumEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_info import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SIGNAL_UPDATE, ThreeiDevice, ThreeiHub
from .const import (
    DOMAIN,
    PROP_CHARGE_STATE,
    PROP_FAULT,
    PROP_WORK_MODE,
    PROP_WORK_STATUS,
    SERVICE_FIND_DEVICE,
    SERVICE_GLOBAL_CLEAN,
    SERVICE_START_RECHARGE,
)


class ThreeiEntity:
    """Shared device info and push-update wiring."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: ThreeiHub, dev: ThreeiDevice) -> None:
        self.hub, self.dev = hub, dev
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, dev.sn)}, name=dev.name, manufacturer="3irobotix", model=str(dev.model)
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE.format(self.dev.sn), self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub: ThreeiHub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(ThreeiVacuum(hub, d) for d in hub.devices.values())


class ThreeiVacuum(ThreeiEntity, StateVacuumEntity):
    _attr_name = None
    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.LOCATE
        | VacuumEntityFeature.STATE
    )

    def __init__(self, hub: ThreeiHub, dev: ThreeiDevice) -> None:
        super().__init__(hub, dev)
        self._attr_unique_id = f"{dev.sn}_vacuum"

    @property
    def activity(self) -> VacuumActivity | None:
        # UNVERIFIED mapping: value enums for work_mode/charge_state are not known yet.
        p = self.dev.props
        if not p:
            return None
        if p.get(PROP_FAULT) not in (None, 0, "0", ""):
            return VacuumActivity.ERROR
        if p.get(PROP_CHARGE_STATE) in (1, "1", True):
            return VacuumActivity.DOCKED
        return VacuumActivity.CLEANING if p.get(PROP_WORK_STATUS) in (1, "1") else VacuumActivity.IDLE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # Raw values so the enums can be worked out from real data.
        return {k: self.dev.props.get(k) for k in (PROP_WORK_MODE, PROP_WORK_STATUS, PROP_CHARGE_STATE, PROP_FAULT)}

    def _invoke(self, service: str, params: dict[str, Any] | None = None) -> None:
        self.hub.mqtt.invoke(self.dev.product_key, self.dev.sn, service, params)

    async def async_start(self) -> None:
        await self.hass.async_add_executor_job(self._invoke, SERVICE_GLOBAL_CLEAN)

    async def async_pause(self) -> None:
        # UNVERIFIED: pause/stop appear to be property writes, value unknown.
        await self.hass.async_add_executor_job(
            self.hub.mqtt.set_properties, self.dev.product_key, self.dev.sn, {PROP_WORK_STATUS: 2}
        )

    async def async_stop(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(
            self.hub.mqtt.set_properties, self.dev.product_key, self.dev.sn, {PROP_WORK_STATUS: 0}
        )

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._invoke, SERVICE_START_RECHARGE)

    async def async_locate(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self._invoke, SERVICE_FIND_DEVICE)
