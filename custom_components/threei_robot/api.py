"""Cloud client for 3irobotix AllInOne devices (HTTP + MQTT)."""
from __future__ import annotations

import hashlib
import json
import logging
import socket
import ssl
import time
import uuid
from collections.abc import Callable
from typing import Any

import aiohttp

from .const import (
    PATH_DEVICE_LIST,
    PATH_LOGIN,
    REGION_URL,
    SIGN_FIELDS,
    TOPIC_PROPERTY_GET,
    TOPIC_PROPERTY_POST,
    TOPIC_PROPERTY_SET,
    TOPIC_SERVICE_INVOKE,
    TOPIC_TEMPLATE,
)

_LOGGER = logging.getLogger(__name__)

# VERIFIED: API and MQTT hosts both serve this self-signed *.3irobotix.net cert
# (also embedded in the app). OpenSSL will not accept it as a trust anchor, so pin it.
CERT_SHA256 = "68a368925db3de516a8064fd7038a34945d86edf113308662c8785a4c9f54a10"
_PIN = aiohttp.Fingerprint(bytes.fromhex(CERT_SHA256))


def _peer_matches_pin(host: str, port: int) -> bool:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=10) as raw, ctx.wrap_socket(raw, server_hostname=host) as t:
        return hashlib.sha256(t.getpeercert(True)).hexdigest() == CERT_SHA256


class ThreeiError(Exception):
    """Cloud returned an error or an unexpected response."""


class ThreeiSignError(ThreeiError):
    """Cloud rejected the request signature (code 889)."""


def _find(obj: Any, *keys: str) -> Any:
    """Depth-first search for the first matching key; response shapes are not yet known."""
    if isinstance(obj, dict):
        for k in keys:
            if obj.get(k) not in (None, ""):
                return obj[k]
        for v in obj.values():
            found = _find(v, *keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find(v, *keys)
            if found is not None:
                return found
    return None


def build_sign(params: dict[str, Any], prefix: str, suffix: str) -> str:
    """UNVERIFIED guess: md5(prefix + sorted k=v joined by & + suffix).

    The app has getSignMD5/_signPrefix/_signSuffix, but the exact recipe and
    the constant values could not be recovered from strings alone.
    """
    body = "&".join(f"{k}={params[k]}" for k in sorted(params) if params[k] is not None)
    return hashlib.md5(f"{prefix}{body}{suffix}".encode()).hexdigest()


class ThreeiCloud:
    """HTTP side: region lookup, login, device list."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        country: str,
        sign_prefix: str = "",
        sign_suffix: str = "",
    ) -> None:
        self._session = session
        self._country = country
        self._sign_prefix = sign_prefix
        self._sign_suffix = sign_suffix
        self.api_base: str | None = None
        self.mqtt_host: str | None = None
        self.mqtt_port: int = 8883
        self.token: str | None = None
        self.user_id: str | None = None
        self.login_result: dict[str, Any] = {}

    async def async_resolve_region(self) -> None:
        async with self._session.get(REGION_URL, ssl=_PIN, timeout=aiohttp.ClientTimeout(total=20)) as r:
            data = await r.json(content_type=None)
        if data.get("code") != 0:
            raise ThreeiError(f"region lookup failed: {data}")
        result = data["result"]
        key = self._country
        for c in result.get("countries", []):
            if c.get("code") == self._country:
                key = c.get("serverKey", key)
                break
        conf = result["serverConfigurations"].get(key) or result["serverConfigurations"]["CN"]
        self.api_base = "https://" + conf["APP_api"].split(":")[0]
        host, _, port = conf["MQTT"].partition(":")
        self.mqtt_host, self.mqtt_port = host, int(port or 8883)
        _LOGGER.debug("region %s -> api %s mqtt %s:%s", key, self.api_base, host, self.mqtt_port)

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        if self.api_base is None:
            await self.async_resolve_region()
        params = {"timestamp": str(int(time.time() * 1000)), "nonce": uuid.uuid4().hex}
        headers = {"Content-Type": "application/json", **params}
        headers["sign"] = build_sign({**params, **body}, self._sign_prefix, self._sign_suffix)
        if self.token:
            headers["Authorization"] = self.token
        _LOGGER.debug("POST %s fields=%s sign_fields=%s", path, sorted(body), SIGN_FIELDS)
        async with self._session.post(
            self.api_base + path, json=body, headers=headers, ssl=_PIN, timeout=aiohttp.ClientTimeout(total=20)
        ) as r:
            data = await r.json(content_type=None)
        _LOGGER.debug("POST %s -> code=%s msg=%s", path, data.get("code"), data.get("msg"))
        if data.get("code") == 889:
            raise ThreeiSignError(data.get("msg", "sign error"))
        if data.get("code") not in (0, 200):
            raise ThreeiError(f"{path}: {data.get('code')} {data.get('msg')}")
        return data.get("result", data.get("data"))

    async def async_login(self, username: str, password: str) -> None:
        # UNVERIFIED body; the app may hash or encrypt the password first.
        result = await self._post(PATH_LOGIN, {"username": username, "password": password})
        self.login_result = result or {}
        self.token = _find(result, "token", "accessToken", "access_token")
        self.user_id = str(_find(result, "userId", "uid", "id") or "")
        if not self.token:
            raise ThreeiError("login succeeded but no token found; enable debug logging and report the keys")
        _LOGGER.debug("login result keys: %s", sorted(self.login_result) if isinstance(self.login_result, dict) else type(self.login_result))

    async def async_get_devices(self) -> list[dict[str, Any]]:
        result = await self._post(PATH_DEVICE_LIST, {"userId": self.user_id})
        if isinstance(result, dict):
            result = _find(result, "list", "records", "devices") or []
        _LOGGER.debug("device list: %s", [sorted(d) for d in result])
        return list(result)


class ThreeiMqtt:
    """MQTT side: property reports in, property set / service invoke out."""

    def __init__(self, host: str, port: int, client_id: str, username: str, password: str) -> None:
        import paho.mqtt.client as mqtt  # imported lazily so config flow works without broker access

        self._mqtt = mqtt
        self._client = mqtt.Client(client_id=client_id, clean_session=True)
        self._client.username_pw_set(username, password)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # replaced by the pin checks in start() and _on_connect()
        self._client.tls_set_context(ctx)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._host, self._port = host, port
        self._subs: list[str] = []
        self.on_properties: Callable[[str, dict[str, Any]], None] | None = None

    @staticmethod
    def topic(pk: str, dn: str, suffix: str) -> str:
        return TOPIC_TEMPLATE.format(pk=pk, dn=dn, suffix=suffix)

    def watch(self, pk: str, dn: str) -> None:
        for suffix in (TOPIC_PROPERTY_POST, TOPIC_PROPERTY_SET + "_reply", "thing/service_invoke_reply/#"):
            self._subs.append(self.topic(pk, dn, suffix))

    def start(self) -> None:
        # Check the pin before paho sends credentials in CONNECT.
        if not _peer_matches_pin(self._host, self._port):
            raise ThreeiError(f"{self._host} certificate does not match the pinned 3irobotix cert")
        self._client.connect_async(self._host, self._port, keepalive=60)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(self, client, userdata, flags, rc) -> None:
        _LOGGER.info("MQTT connect rc=%s", rc)
        sock = client.socket()
        if sock is None or hashlib.sha256(sock.getpeercert(True)).hexdigest() != CERT_SHA256:
            _LOGGER.error("MQTT peer certificate does not match the pin; disconnecting")
            client.disconnect()
            return
        for t in self._subs:
            client.subscribe(t, qos=1)

    def _on_message(self, client, userdata, msg) -> None:
        _LOGGER.debug("MQTT %s %s", msg.topic, msg.payload[:500])
        try:
            payload = json.loads(msg.payload)
        except ValueError:
            return
        params = payload.get("params", payload.get("data", payload))
        if isinstance(params, dict) and self.on_properties:
            self.on_properties(msg.topic, params)

    def _publish(self, topic: str, method: str, params: dict[str, Any]) -> None:
        body = {"id": str(int(time.time() * 1000)), "version": "1.0", "method": method, "params": params}
        _LOGGER.debug("MQTT publish %s %s", topic, body)
        self._client.publish(topic, json.dumps(body), qos=1)

    def request_properties(self, pk: str, dn: str) -> None:
        self._publish(self.topic(pk, dn, TOPIC_PROPERTY_GET), "thing.service.property.get", {})

    def set_properties(self, pk: str, dn: str, props: dict[str, Any]) -> None:
        self._publish(self.topic(pk, dn, TOPIC_PROPERTY_SET), "thing.service.property.set", props)

    def invoke(self, pk: str, dn: str, service: str, params: dict[str, Any] | None = None) -> None:
        self._publish(self.topic(pk, dn, TOPIC_SERVICE_INVOKE + service), f"thing.service.{service}", params or {})

