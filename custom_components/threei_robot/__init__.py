"""3irobotix AllInOne (F1 Pro) integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import ThreeiCloud, ThreeiError, ThreeiMqtt, _find
from .const import CONF_COUNTRY, CONF_SIGN_PREFIX, CONF_SIGN_SUFFIX, DOMAIN

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.VACUUM, Platform.SENSOR]
SIGNAL_UPDATE = f"{DOMAIN}_update_{{}}"


class ThreeiDevice:
    """One bound robot and its last known properties."""

    def __init__(self, raw: dict[str, Any]) -> None:
        self.raw = raw
        self.sn = str(_find(raw, "sn", "deviceSn", "deviceName"))
        self.product_key = str(_find(raw, "productKey", "productId") or "")
        self.name = _find(raw, "nickname", "nickName", "deviceNickname") or f"Robot {self.sn[-4:]}"
        self.model = _find(raw, "productModeCode", "model", "productName") or "unknown"
        self.props: dict[str, Any] = {}


class ThreeiHub:
    def __init__(self, hass: HomeAssistant, cloud: ThreeiCloud, mqtt: ThreeiMqtt, devices: list[ThreeiDevice]) -> None:
        self.hass, self.cloud, self.mqtt = hass, cloud, mqtt
        self.devices = {d.sn: d for d in devices}
        mqtt.on_properties = self._on_properties

    def _on_properties(self, topic: str, params: dict[str, Any]) -> None:
        # Runs in paho's thread; hop to the event loop.
        self.hass.loop.call_soon_threadsafe(self._apply, topic, params)

    @callback
    def _apply(self, topic: str, params: dict[str, Any]) -> None:
        for dev in self.devices.values():
            if dev.sn in topic:
                for k, v in params.items():
                    dev.props[k] = v.get("value", v) if isinstance(v, dict) else v
                async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(dev.sn))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    cloud = ThreeiCloud(
        async_get_clientsession(hass),
        entry.data[CONF_COUNTRY].upper(),
        entry.data.get(CONF_SIGN_PREFIX, ""),
        entry.data.get(CONF_SIGN_SUFFIX, ""),
    )
    try:
        await cloud.async_login(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
        devices = [ThreeiDevice(d) for d in await cloud.async_get_devices()]
    except ThreeiError as err:
        raise ConfigEntryNotReady(str(err)) from err

    # UNVERIFIED: which login fields are the MQTT credentials.
    mqtt_pwd = _find(cloud.login_result, "emqToken", "mqttToken", "mqttPassword") or cloud.token
    mqtt_user = _find(cloud.login_result, "mqttUsername", "mqttUser") or cloud.user_id
    mqtt = ThreeiMqtt(cloud.mqtt_host, cloud.mqtt_port, f"ha_{cloud.user_id}_{entry.entry_id[:8]}", mqtt_user, mqtt_pwd)
    for d in devices:
        mqtt.watch(d.product_key, d.sn)
    try:
        await hass.async_add_executor_job(mqtt.start)
    except (ThreeiError, OSError) as err:
        raise ConfigEntryNotReady(f"MQTT: {err}") from err

    hub = ThreeiHub(hass, cloud, mqtt, devices)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    for d in devices:
        await hass.async_add_executor_job(mqtt.request_properties, d.product_key, d.sn)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hub: ThreeiHub = hass.data[DOMAIN].pop(entry.entry_id)
        await hass.async_add_executor_job(hub.mqtt.stop)
    return ok
