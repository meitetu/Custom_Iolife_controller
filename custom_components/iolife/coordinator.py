"""Data update coordinator for the Toshiba IoLIFE integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import api
from .const import (
    CONF_EMAIL,
    CONF_HUMIDITY_SENSOR,
    CONF_LANGUAGE,
    CONF_PASSWORD,
    CONF_TEMPERATURE_SENSOR,
    DEFAULT_LANGUAGE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

APPLIANCE_AC = "0xAC"


@dataclass
class IolifeData:
    """One appliance's polled state."""

    appliance_id: str
    name: str
    values: Dict[int, Any]
    room_temperature: float | None = None
    room_humidity: float | None = None


def _read_sensor(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Return a numeric sensor state, or None when unavailable."""
    if not entity_id:
        return None
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", ""):
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        _LOGGER.warning("%s is not numeric: %s", entity_id, state.state)
        return None


class IolifeCoordinator(DataUpdateCoordinator[Dict[str, IolifeData]]):
    """Poll every configured appliance in a single request round."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.entry = entry
        self._http: aiohttp.ClientSession | None = None
        self.client: api.IolifeClient | None = None
        self.appliances: list[dict[str, Any]] = []

    async def _async_setup(self) -> None:
        self._http = aiohttp.ClientSession()
        self.client = api.IolifeClient(
            self._http,
            self.entry.data[CONF_EMAIL],
            self.entry.data[CONF_PASSWORD],
            self.entry.data.get(CONF_LANGUAGE, DEFAULT_LANGUAGE),
        )
        try:
            await self.client.async_login()
        except api.IolifeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except api.IolifeError as err:
            raise ConfigEntryNotReady(str(err)) from err

        try:
            devices = await self.client.async_list_devices()
        except api.IolifeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except api.IolifeError as err:
            raise ConfigEntryNotReady(str(err)) from err

        self.appliances = [
            d for d in devices if str(d.get("type")).upper() == APPLIANCE_AC.upper()
        ]
        if not self.appliances:
            raise ConfigEntryNotReady("no 0xAC appliances found on this account")

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self._http is not None:
            await self._http.close()
            self._http = None

    async def _async_update_data(self) -> Dict[str, IolifeData]:
        assert self.client is not None
        # External sensors are read from the state machine, so a slow or
        # sleeping AC still gets a room temperature in the UI.
        temperature = _read_sensor(
            self.hass, self.entry.data.get(CONF_TEMPERATURE_SENSOR)
        )
        humidity = _read_sensor(self.hass, self.entry.data.get(CONF_HUMIDITY_SENSOR))

        result: Dict[str, IolifeData] = {}
        for appliance in self.appliances:
            appliance_id = str(appliance["id"])
            try:
                values = await self.client.async_query_properties(appliance_id)
            except api.IolifeAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except api.IolifeTimeoutError as err:
                # A single sleeping appliance must not fail the whole entry.
                _LOGGER.warning("appliance %s did not answer: %s", appliance_id, err)
                continue
            except api.IolifeError as err:
                raise UpdateFailed(f"{appliance_id}: {err}") from err
            result[appliance_id] = IolifeData(
                appliance_id=appliance_id,
                name=str(appliance.get("name") or appliance_id),
                values=values,
                room_temperature=temperature,
                room_humidity=humidity,
            )
        return result

    async def async_apply(self, appliance_id: str, settings: list[tuple[int, list[int]]]) -> None:
        """Send one multi-property frame (single beep) and refresh."""
        assert self.client is not None
        try:
            await self.client.async_set_properties(appliance_id, settings)
        except api.IolifeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except api.IolifeError as err:
            raise UpdateFailed(str(err)) from err
        await self.async_request_refresh()
