"""Constants for the Toshiba IoLIFE integration."""
from __future__ import annotations

DOMAIN = "iolife"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_APPLIANCES = "appliances"
CONF_LANGUAGE = "language"

DEFAULT_LANGUAGE = "ja_JP"
DEFAULT_SCAN_INTERVAL = 60

# Verified control surface of a Type 0xAC appliance. Anything outside this list
# was measured to be acknowledged but silently ignored by the unit.
SUPPORTED_HVAC_MODES = ["auto", "cool", "dry", "heat", "fan"]
SUPPORTED_FAN_MODES = ["auto", "strong", "mid", "weak", "mute"]
