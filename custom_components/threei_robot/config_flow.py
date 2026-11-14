"""Config flow for 3irobotix."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ThreeiCloud, ThreeiError, ThreeiSignError
from .const import CONF_COUNTRY, CONF_SIGN_PREFIX, CONF_SIGN_SUFFIX, DEFAULT_COUNTRY, DOMAIN

_LOGGER = logging.getLogger(__name__)

SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_COUNTRY, default=DEFAULT_COUNTRY): str,
        vol.Optional(CONF_SIGN_PREFIX, default=""): str,
        vol.Optional(CONF_SIGN_SUFFIX, default=""): str,
    }
)


class ThreeiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()
            cloud = ThreeiCloud(
                async_get_clientsession(self.hass),
                user_input[CONF_COUNTRY].upper(),
                user_input[CONF_SIGN_PREFIX],
                user_input[CONF_SIGN_SUFFIX],
            )
            try:
                await cloud.async_login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            except ThreeiSignError:
                errors["base"] = "sign"
            except ThreeiError as err:
                _LOGGER.warning("login failed: %s", err)
                errors["base"] = "auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("unexpected error during login")
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title=user_input[CONF_USERNAME], data=user_input)
        return self.async_show_form(step_id="user", data_schema=SCHEMA, errors=errors)
