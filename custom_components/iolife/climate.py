"""Climate entity for a Toshiba IoLIFE 0xAC appliance."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import api
from .const import DOMAIN, SUPPORTED_FAN_MODES
from .coordinator import IolifeCoordinator, IolifeData

_LOGGER = logging.getLogger(__name__)

HVAC_MODES = [
    HVACMode.OFF,
    HVACMode.AUTO,
    HVACMode.COOL,
    HVACMode.DRY,
    HVACMode.HEAT,
    HVACMode.FAN_ONLY,
]

MODE_TO_API = {
    HVACMode.AUTO: "auto",
    HVACMode.COOL: "cool",
    HVACMode.DRY: "dry",
    HVACMode.HEAT: "heat",
    HVACMode.FAN_ONLY: "fan",
}
API_TO_MODE = {v: k for k, v in MODE_TO_API.items()}

# Fan codes. "mute" is the AC's "おやすみ" (quiet) setting.
API_FAN = api.AC_FAN_SPEEDS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IolifeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        IolifeClimate(coordinator, str(appliance["id"]), str(appliance.get("name") or "IoLIFE AC"))
        for appliance in coordinator.appliances
    )


class IolifeClimate(CoordinatorEntity[IolifeCoordinator], ClimateEntity):
    """A Toshiba IoLIFE air conditioner."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = api.AC_TEMPERATURE_STEP
    _attr_min_temp = api.AC_TEMPERATURE_MIN
    _attr_max_temp = api.AC_TEMPERATURE_MAX
    _attr_hvac_modes = HVAC_MODES
    _attr_fan_modes = SUPPORTED_FAN_MODES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
    )
    _attr_swing_modes = ["off", "vertical", "horizontal", "both"]
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: IolifeCoordinator, appliance_id: str, name: str) -> None:
        super().__init__(coordinator)
        self._appliance_id = appliance_id
        self._attr_unique_id = f"{DOMAIN}_{appliance_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, appliance_id)},
            name=name,
            manufacturer="Toshiba",
            model="IoLIFE 0xAC",
        )

    # -- helpers -----------------------------------------------------------
    @property
    def _entry(self) -> IolifeData | None:
        return (self.coordinator.data or {}).get(self._appliance_id)

    @property
    def _values(self) -> dict[int, Any]:
        entry = self._entry
        return entry.values if entry else {}

    @property
    def available(self) -> bool:
        return self._appliance_id in (self.coordinator.data or {})

    # -- state -------------------------------------------------------------
    @property
    def native_current_temperature(self) -> float | None:
        """Prefer the configured room sensor, fall back to the AC's own value."""
        entry = self._entry
        if entry and entry.room_temperature is not None:
            return entry.room_temperature
        return self._values.get(api.PROP_INDOOR_TEMP)

    @property
    def native_target_temperature(self) -> float | None:
        return self._values.get(api.PROP_TARGET_TEMP)

    @property
    def hvac_mode(self) -> HVACMode | None:
        values = self._values
        if not values.get(api.PROP_POWER):
            return HVACMode.OFF
        return API_TO_MODE.get(values.get(api.PROP_MODE, ""), HVACMode.AUTO)

    @property
    def fan_mode(self) -> str | None:
        return self._values.get(api.PROP_FAN)

    @property
    def swing_mode(self) -> str | None:
        ud = bool(self._values.get(api.PROP_SWING_UD))
        lr = bool(self._values.get(api.PROP_SWING_LR))
        if ud and lr:
            return "both"
        if ud:
            return "vertical"
        if lr:
            return "horizontal"
        return "off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        values = self._values
        entry = self._entry
        return {
            # The AC's own reading, kept for comparison with the room sensor.
            "ac_indoor_temperature": values.get(api.PROP_INDOOR_TEMP),
            "outdoor_temperature": values.get(api.PROP_OUTDOOR_TEMP),
            "indoor_humidity": (
                entry.room_humidity if entry and entry.room_humidity is not None
                else values.get(api.PROP_HUMIDITY)
            ),
            "eco": values.get(api.PROP_ECO),
            "purifier": values.get(api.PROP_PURIFIER),
            "error_code": values.get(api.PROP_ERROR_CODE),
        }

    # -- commands ----------------------------------------------------------
    def _mode_setting(self, mode: HVACMode) -> tuple[int, list[int]]:
        return api.PROP_MODE, [api.AC_OPERATION_MODES[MODE_TO_API[mode]]]

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        # Power and mode travel in one frame so the unit beeps once.
        if hvac_mode == HVACMode.OFF:
            settings = [(api.PROP_POWER, [0])]
        else:
            settings = [(api.PROP_POWER, [1]), self._mode_setting(hvac_mode)]
        await self.coordinator.async_apply(self._appliance_id, settings)

    async def async_turn_on(self) -> None:
        await self.coordinator.async_apply(self._appliance_id, [(api.PROP_POWER, [1])])

    async def async_turn_off(self) -> None:
        await self.coordinator.async_apply(self._appliance_id, [(api.PROP_POWER, [0])])

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        clamped = max(
            api.AC_TEMPERATURE_MIN, min(api.AC_TEMPERATURE_MAX, round(temperature * 2) / 2)
        )
        raw = int(round(clamped * 2))
        await self.coordinator.async_apply(
            self._appliance_id, [(api.PROP_TARGET_TEMP, [raw])]
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        code = API_FAN.get(fan_mode)
        if code is None:
            _LOGGER.warning("unsupported fan mode %s", fan_mode)
            return
        await self.coordinator.async_apply(self._appliance_id, [(api.PROP_FAN, [code])])

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        ud = swing_mode in ("vertical", "both")
        lr = swing_mode in ("horizontal", "both")
        await self.coordinator.async_apply(
            self._appliance_id,
            [(api.PROP_SWING_UD, [1 if ud else 0]), (api.PROP_SWING_LR, [1 if lr else 0])],
        )
