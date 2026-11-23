"""Config flow for the Toshiba IoLIFE integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import aiohttp_client, selector

from . import api
from .const import (
    CONF_EMAIL,
    CONF_HUMIDITY_SENSOR,
    CONF_LANGUAGE,
    CONF_PASSWORD,
    CONF_TEMPERATURE_SENSOR,
    DEFAULT_LANGUAGE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_LANGUAGE, default=DEFAULT_LANGUAGE): str,
    }
)


class IolifeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup for an IoLIFE account."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = aiohttp_client.async_get_clientsession(self.hass)
            client = api.IolifeClient(
                session,
                user_input[CONF_EMAIL],
                user_input[CONF_PASSWORD],
                user_input.get(CONF_LANGUAGE, DEFAULT_LANGUAGE),
            )
            try:
                await client.async_login()
                devices = await client.async_list_devices()
            except api.IolifeAuthError:
                errors["base"] = "invalid_auth"
            except (api.IolifeError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - HA wants a friendly message
                _LOGGER.exception("unexpected error during setup")
                errors["base"] = "unknown"
            else:
                if not any(str(d.get("type")).upper() == "0XAC" for d in devices):
                    errors["base"] = "no_devices"
                else:
                    await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                    self._abort_if_unique_id_configured()
                    self._credentials = user_input
                    return await self.async_step_sensors()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Optionally pick external room temperature / humidity sensors."""
        if user_input is not None:
            data = {**self._credentials, **user_input}
            return self.async_create_entry(
                title=self._credentials[CONF_EMAIL], data=data
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_TEMPERATURE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_HUMIDITY_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )
        return self.async_show_form(step_id="sensors", data_schema=schema)
