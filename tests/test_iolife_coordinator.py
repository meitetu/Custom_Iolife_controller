"""Tests for the coordinator sensor plumbing. No network access."""
from custom_components.iolife.const import (
    CONF_HUMIDITY_SENSOR,
    CONF_TEMPERATURE_SENSOR,
)


class _State:
    def __init__(self, state):
        self.state = state


class _States:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, entity_id):
        value = self._mapping.get(entity_id)
        return _State(value) if value is not None else None


class _Hass:
    def __init__(self, mapping):
        self.states = _States(mapping)


def test_read_sensor_returns_float():
    from custom_components.iolife.coordinator import _read_sensor

    hass = _Hass({"sensor.room": "23.9"})
    assert _read_sensor(hass, "sensor.room") == 23.9


def test_read_sensor_handles_missing_and_unknown():
    from custom_components.iolife.coordinator import _read_sensor

    hass = _Hass({"sensor.bad": "unavailable", "sensor.text": "warm"})
    assert _read_sensor(hass, "sensor.missing") is None
    assert _read_sensor(hass, "sensor.bad") is None
    assert _read_sensor(hass, "sensor.text") is None
    assert _read_sensor(hass, None) is None


def test_sensor_keys_exist_in_const():
    assert CONF_TEMPERATURE_SENSOR == "temperature_sensor"
    assert CONF_HUMIDITY_SENSOR == "humidity_sensor"
