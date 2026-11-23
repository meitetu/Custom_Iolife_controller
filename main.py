#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import itertools
import json
import pathlib
import random
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

try:
    from Crypto.Cipher import AES
except Exception:  # pragma: no cover
    AES = None


HOST = "app.iolife.toshiba-lifestyle.com"
SERVER_VERSION = "v1"
SCHEME = "https"
APP_ID = "1203"
APP_KEY = "09c4d09f0da1513bb62dc7b6b0af9c11"
APP_SRC = "203"
CLIENT_TYPE = "1"
APP_ENTERPRISE = "0008"
DEFAULT_LANGUAGE = "ja_JP"
DEFAULT_APP_VERSION = "3.3.2"
SESSION_FILE = pathlib.Path(__file__).resolve().parent / "session.json"
MESSAGE_COUNTER = itertools.count(1)
AC_DEVICE_TYPE = 0xAC
AC_REQUEST_CONTROL = 0x0002
AC_REQUEST_QUERY = 0x0003
AC_CONTROL_PROPERTY_CMD = 0xB0
AC_QUERY_PROPERTY_CMD = 0xB1
AC_OPERATION_MODES: Dict[str, int] = {
    "auto": 0x01,
    "cool": 0x02,
    "dry": 0x03,
    "heat": 0x04,
    "fan": 0x05,
    "smart_dry": 0x06,
}
AC_FAN_SPEEDS: Dict[str, int] = {
    "auto": 0x00,
    "strong": 0x50,
    "mid": 0x3C,
    "weak": 0x14,
    "mute": 0x01,
}
AC_TEMPERATURE_MIN = 16
AC_TEMPERATURE_MAX = 32
AC_RESPONSE_ID_PROPERTIES_ACK = 0xB0
AC_RESPONSE_ID_PROPERTIES = 0xB1
AC_RESPONSE_ID_STATE = 0xC0
# Curated set of properties the AC can report in a single B1 query.
# Verified on RAS-G221E8P(W): 21 properties in one reply.
AC_ALL_PROPERTIES: List[int] = [
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A,
    0x0D, 0x0E, 0x10, 0x14, 0x15, 0x17, 0x18, 0x1A, 0x3F, 0x47, 0x48,
]
# How each property value is scaled on the wire.
# 0x03 and 0x06 are single bytes; 0x04/0x05 use Midea's (raw-50)/2 + decimals/10
# and are decoded specially (see decode_ac_property_value).
AC_PROPERTY_DIVISORS: Dict[int, int] = {
    0x03: 2,
}
# Properties whose raw value is two bytes: temperature base then decimals.
AC_TEMPERATURE_PROPERTIES = {0x04, 0x05}
AC_FAN_NAME_BY_VALUE: Dict[int, str] = {
    0x66: "auto",
    0x50: "strong",
    0x3C: "mid",
    0x14: "weak",
    0x01: "mute",
}
AC_MODE_NAME_BY_VALUE: Dict[int, str] = {value: name for name, value in AC_OPERATION_MODES.items()}
AC_MODE_NAME_BY_VALUE[0] = "off"
AC_PROPERTY_NAMES: Dict[int, str] = {
    0x01: "power",
    0x02: "mode",
    0x03: "temperature",
    0x04: "indoor_temperature",
    0x05: "outdoor_temperature",
    0x06: "wind_speed",
    0x07: "wind_speed_real",
    0x08: "wind_swing_ud",
    0x09: "wind_swing_lr",
    0x0A: "wind_deflector",
    0x0B: "power_on_timer",
    0x0C: "power_off_timer",
    0x0D: "eco",
    0x0E: "purifier",
    0x10: "dry",
    0x14: "humidity",
    0x15: "indoor_humidity",
    0x17: "screen_display",
    0x18: "no_wind_sense",
    0x1A: "buzzer",
    0x3F: "error_code_query",
    0x47: "high_temperature_monitor",
    0x48: "rate_select",
}
AC_QUERY_PROPERTIES: Dict[str, int] = {
    "power": 0x01,
    "mode": 0x02,
    "temperature": 0x03,
    "indoor_temperature": 0x04,
    "outdoor_temperature": 0x05,
    "wind_speed": 0x06,
    "wind_speed_real": 0x07,
    "wind_swing_ud": 0x08,
    "wind_swing_lr": 0x09,
    "wind_deflector": 0x0A,
    "power_on_timer": 0x0B,
    "power_off_timer": 0x0C,
    "eco": 0x0D,
    "purifier": 0x0E,
    "dry": 0x10,
    "humidity": 0x14,
    "indoor_humidity": 0x15,
    "screen_display": 0x17,
    "no_wind_sense": 0x18,
    "buzzer": 0x1A,
    "error_code_query": 0x3F,
    "mode_query": 0x41,
    "clean": 0x46,
    "high_temperature_monitor": 0x47,
    "rate_select": 0x48,
    "power_on_timer_specific": 0x53,
    "power_off_timer_specific": 0x54,
    "timer_expired": 0x60,
    "timer_setting": 0x61,
    "new_no_wind_sense": 0x70,
    "wind_radar": 0x71,
    "area": 0x72,
    "way_out": 0x73,
    "quick_mode": 0x74,
    "change_air": 0x75,
    "air_clean_switch": 0x76,
    "circle_fan": 0x79,
    "eco_power_saving": 0x7A,
    "weak_cool": 0x7B,
    "high_temperature_wind": 0x7C,
    "manual_defrost": 0x7D,
}
CRC8_854_TABLE = [
    0, 94, 188, 226, 97, 63, 221, 131, 194, 156, 126, 32, 163, 253, 31, 65,
    157, 195, 33, 127, 252, 162, 64, 30, 95, 1, 227, 189, 62, 96, 130, 220,
    35, 125, 159, 193, 66, 28, 254, 160, 225, 191, 93, 3, 128, 222, 60, 98,
    190, 224, 2, 92, 223, 129, 99, 61, 124, 34, 192, 158, 29, 67, 161, 255,
    70, 24, 250, 164, 39, 121, 155, 197, 132, 218, 56, 102, 229, 187, 89, 7,
    219, 133, 103, 57, 186, 228, 6, 88, 25, 71, 165, 251, 120, 38, 196, 154,
    101, 59, 217, 135, 4, 90, 184, 230, 167, 249, 27, 69, 198, 152, 122, 36,
    248, 166, 68, 26, 153, 199, 37, 123, 58, 100, 134, 216, 91, 5, 231, 185,
    140, 210, 48, 110, 237, 179, 81, 15, 78, 16, 242, 172, 47, 113, 147, 205,
    17, 79, 173, 243, 112, 46, 204, 146, 211, 141, 111, 49, 178, 236, 14, 80,
    175, 241, 19, 77, 206, 144, 114, 44, 109, 51, 209, 143, 12, 82, 176, 238,
    50, 108, 142, 208, 83, 13, 239, 177, 240, 174, 76, 18, 145, 207, 45, 115,
    202, 148, 118, 40, 171, 245, 23, 73, 8, 86, 180, 234, 105, 55, 213, 139,
    87, 9, 235, 181, 54, 104, 138, 212, 149, 203, 41, 119, 244, 170, 72, 22,
    233, 183, 85, 11, 136, 214, 52, 106, 43, 117, 151, 201, 74, 20, 246, 168,
    116, 42, 200, 150, 21, 75, 169, 247, 182, 232, 10, 84, 215, 137, 107, 53,
]


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().lower()


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().lower()


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
    if not data or len(data) % block_size != 0:
        raise ValueError("invalid AES block data")
    pad_len = data[-1]
    if pad_len <= 0 or pad_len > block_size:
        raise ValueError("invalid PKCS7 padding")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("invalid PKCS7 padding bytes")
    return data[:-pad_len]


def aes_encrypt_hex(plain_text: str, key_text: str, iv_text: Optional[str] = None) -> str:
    if AES is None:
        raise RuntimeError("pycryptodome is required: pip install -r requirements.txt")
    key = key_text.encode("utf-8")
    data = pkcs7_pad(plain_text.encode("utf-8"))
    if iv_text:
        iv = iv_text.encode("utf-8")
        cipher = AES.new(key, AES.MODE_CBC, iv)
    else:
        cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(data).hex()


def aes_decrypt_hex(cipher_hex: str, key_text: str, iv_text: Optional[str] = None) -> str:
    if AES is None:
        raise RuntimeError("pycryptodome is required: pip install -r requirements.txt")
    key = key_text.encode("utf-8")
    raw = bytes.fromhex(cipher_hex)
    if iv_text:
        iv = iv_text.encode("utf-8")
        cipher = AES.new(key, AES.MODE_CBC, iv)
    else:
        cipher = AES.new(key, AES.MODE_ECB)
    return pkcs7_unpad(cipher.decrypt(raw)).decode("utf-8")


def app_key_crypto_key(app_key: str) -> str:
    return md5_hex(app_key)[:16]


def decode_with_app_key(cipher_hex: str, app_key: str) -> str:
    # encodeIv() is effectively null in this build, so AES/ECB is used.
    return aes_decrypt_hex(cipher_hex, app_key_crypto_key(app_key), None)


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d%H%M%S")


def signed_byte(value: int) -> int:
    return value - 256 if value > 127 else value


def bytes_to_dec_string(data: bytes) -> str:
    return ",".join(str(signed_byte(b)) for b in data)


def dec_string_to_bytes(data: str) -> bytes:
    values: List[int] = []
    for part in data.split(","):
        part = part.strip()
        if not part:
            continue
        value = int(part)
        values.append((value + 256) % 256)
    return bytes(values)


def timestamp_bytes() -> bytes:
    now = dt.datetime.now()
    year = now.year
    return bytes(
        [
            (now.microsecond // 1000) & 0xFF,
            now.second & 0xFF,
            now.minute & 0xFF,
            (now.hour % 12) & 0xFF,  # Java Calendar.HOUR
            now.day & 0xFF,
            (now.month - 1) & 0xFF,  # Java Calendar.MONTH
            (year % 100) & 0xFF,
            (year // 100) & 0xFF,
        ]
    )


def build_wifidatagram(payload_hex: str, appliance_id: str, msg_type: int = 32, msg_id: Optional[int] = None) -> bytes:
    body = bytes.fromhex(payload_hex)
    msg_id = next(MESSAGE_COUNTER) if msg_id is None else msg_id
    dev_id = int(appliance_id).to_bytes(8, "little", signed=False)[:6]
    length = len(body) + 56
    packet = bytearray()
    packet += b"\x5A\x5A"
    packet += b"\x01"  # version
    packet += b"\x00"  # encrypt/sign flags
    packet += length.to_bytes(2, "little", signed=False)
    packet += int(msg_type).to_bytes(2, "little", signed=False)
    packet += int(msg_id).to_bytes(4, "little", signed=False)
    packet += timestamp_bytes()
    packet += dev_id
    packet += b"\x00\x00"  # resp timeout
    packet += bytes(6)  # channel id
    packet += bytes(6)  # reserve
    packet += body
    packet += bytes(16)  # signature (none)
    if len(packet) != length:
        raise ValueError(f"datagram length mismatch: expected={length}, actual={len(packet)}")
    return bytes(packet)


def parse_wifidatagram(data: bytes) -> Dict[str, Any]:
    if len(data) < 56 or data[0:2] != b"\x5A\x5A":
        raise ValueError("invalid datagram")
    length = int.from_bytes(data[4:6], "little", signed=False)
    msg_type = int.from_bytes(data[6:8], "little", signed=False)
    msg_id = int.from_bytes(data[8:12], "little", signed=False)
    body_len = length - 56
    body = data[40 : 40 + body_len] if body_len > 0 else b""
    return {
        "length": length,
        "msgType": msg_type,
        "msgId": msg_id,
        "devIdHex": data[20:26].hex(),
        "bodyHex": body.hex().upper(),
        "rawHex": data.hex().upper(),
    }


def crc16_ccitt(data: List[int], start_pos: int, end_pos: int) -> int:
    crc = 0
    for si in range(start_pos, end_pos + 1):
        crc ^= (data[si] << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def crc8_854(data: List[int], start_pos: int, end_pos: int) -> int:
    crc = 0
    for si in range(start_pos, end_pos + 1):
        crc = CRC8_854_TABLE[(crc ^ data[si]) & 0xFF]
    return crc


def build_ac_uart_payload(body: List[int], request_type: int) -> bytes:
    body_length = len(body)
    msg_length = body_length + 0x10 + 2
    msg = [0] * msg_length
    msg[0] = 0x55
    msg[1] = 0xAA
    msg[2] = 0xCC
    msg[3] = 0x33
    msg_len = msg_length - 4
    msg[4] = msg_len & 0xFF
    msg[5] = (msg_len >> 8) & 0xFF
    msg[6] = 0x01
    msg[7] = AC_DEVICE_TYPE
    msg[14] = request_type & 0xFF
    msg[15] = (request_type >> 8) & 0xFF
    for i, value in enumerate(body):
        msg[0x10 + i] = value & 0xFF
    crc = crc16_ccitt(msg, 0, msg_length - 3)
    msg[msg_length - 2] = crc & 0xFF
    msg[msg_length - 1] = (crc >> 8) & 0xFF
    return bytes(msg)


def build_ac_query_payload(query_type: str = "all") -> bytes:
    query_type = (query_type or "all").strip().lower()
    if query_type in {"all", "*"}:
        body = [0] * 22
        body[0] = 0x41
        body[1] = 0x81
        body[3] = 0xFF
        body[20] = random.randint(1, 254)
        body[21] = crc8_854(body, 0, 20)
        return build_ac_uart_payload(body, AC_REQUEST_QUERY)

    prop_code = AC_QUERY_PROPERTIES.get(query_type)
    if prop_code is None:
        supported = ", ".join(sorted(AC_QUERY_PROPERTIES.keys()))
        raise ValueError(f"unsupported --query-type '{query_type}'. use: all, {supported}")

    body = [AC_QUERY_PROPERTY_CMD, 1, prop_code, 0x00]
    body.append(random.randint(1, 254))
    body.append(0x00)
    body[-1] = crc8_854(body, 0, len(body) - 2)
    return build_ac_uart_payload(body, AC_REQUEST_QUERY)


def build_ac_power_payload(state: str) -> bytes:
    return build_ac_control_payload(0x01, [1 if state.lower() == "on" else 0])


def build_ac_control_payload(prop_code: int, values: List[int]) -> bytes:
    body = [AC_CONTROL_PROPERTY_CMD, 1, prop_code, 0x00, len(values)]
    body.extend(value & 0xFF for value in values)
    body.append(random.randint(1, 254))
    body.append(0x00)
    body[-1] = crc8_854(body, 0, len(body) - 2)
    return build_ac_uart_payload(body, AC_REQUEST_CONTROL)


def build_ac_mode_payload(mode: str) -> bytes:
    return build_ac_control_payload(*build_ac_control_settings(mode=mode)[0])


def build_ac_temperature_payload(temperature: float) -> bytes:
    return build_ac_control_payload(*build_ac_control_settings(temperature=temperature)[0])


def build_ac_fan_payload(fan: str) -> bytes:
    return build_ac_control_payload(*build_ac_control_settings(fan=fan)[0])


def build_ac_query_properties_payload(prop_codes: List[int]) -> bytes:
    """Build a multi-property query (B1 <count> <id LE16>...)."""
    if not prop_codes:
        raise ValueError("at least one property code is required")
    body = [AC_QUERY_PROPERTY_CMD, len(prop_codes)]
    for prop_code in prop_codes:
        body.extend([prop_code & 0xFF, (prop_code >> 8) & 0xFF])
    body.append(random.randint(1, 254))
    body.append(0x00)
    body[-1] = crc8_854(body, 0, len(body) - 2)
    return build_ac_uart_payload(body, AC_REQUEST_QUERY)


def build_ac_set_properties_payload(values: List[Tuple[int, List[int]]]) -> bytes:
    """Build a multi-property control frame (B0 <count> <id LE16><size><value>...).

    Sending several settings in a single frame keeps the AC beep to one.
    Note: control frames have no result byte; that byte only appears in replies.
    """
    if not values:
        raise ValueError("at least one property is required")
    body = [AC_CONTROL_PROPERTY_CMD, len(values)]
    for prop_code, raw in values:
        body.extend([prop_code & 0xFF, (prop_code >> 8) & 0xFF, len(raw)])
        body.extend(value & 0xFF for value in raw)
    body.append(random.randint(1, 254))
    body.append(0x00)
    body[-1] = crc8_854(body, 0, len(body) - 2)
    return build_ac_uart_payload(body, AC_REQUEST_CONTROL)


def decode_ac_temperature(raw_base: int, decimals: int) -> Optional[float]:
    """Decode a Midea-style temperature: (raw - 50) / 2 plus a decimal nibble.

    0xFF and 0x32 are sentinels. 0x32 decodes to 0.0C by formula, but the unit
    sends it for the outdoor sensor while idle, so it is reported as missing.
    """
    if raw_base in (0xFF, 0x32):
        return None
    base = (raw_base - 50) / 2
    fraction = decimals / 10
    return base + (fraction if base >= 0 else -fraction)


def decode_ac_property_value(prop_code: int, raw: bytes) -> Any:
    """Decode a property value.

    0x04/0x05 carry a temperature byte plus a decimal byte; other properties
    use their first byte directly.
    """
    if not raw:
        return None
    if prop_code in AC_TEMPERATURE_PROPERTIES and len(raw) >= 2:
        return decode_ac_temperature(raw[0], raw[1])
    value = raw[0]
    divisor = AC_PROPERTY_DIVISORS.get(prop_code)
    if divisor:
        return value / divisor
    return value


def parse_ac_properties_response(body: bytes) -> List[Dict[str, Any]]:
    """Parse a B0/B1 TLV body into a list of property entries."""
    if len(body) < 2:
        raise ValueError("property response body is too short")
    count = body[1]
    cursor = 2
    entries: List[Dict[str, Any]] = []
    for _ in range(count):
        if len(body) - cursor < 4:
            break
        prop_code = int.from_bytes(body[cursor : cursor + 2], "little")
        result = body[cursor + 2]
        size = body[cursor + 3]
        raw = body[cursor + 4 : cursor + 4 + size]
        cursor += 4 + size
        entries.append(
            {
                "property": prop_code,
                "name": AC_PROPERTY_NAMES.get(prop_code, "unknown"),
                "result": result,
                "error": bool(result & 0x10),
                "size": size,
                "rawHex": raw.hex().upper(),
                "value": decode_ac_property_value(prop_code, raw),
            }
        )
    return entries


AC_RUN_MODE_NAMES: Dict[int, str] = {
    0: "off",
    1: "cooling",
    2: "cooling",
    3: "dry",
    4: "heating",
    5: "fan",
}


def decode_ac_state_body(body: bytes) -> Dict[str, Any]:
    """Decode a 0xC0 all-state body.

    Verified against the multi-property query on RAS-G221E8P(W):
    target temperature is in payload[4] (0.5C steps, bit 7 is a flag), the
    operation mode in payload[2] bits 4-6, and the fan speed in payload[3].
    Temperatures use Midea's (raw - 50) / 2 decoding.

    payload[19]/[20] clearly react to louver swing commands and are exposed
    raw; their exact encoding is not confirmed (values drift between runs, so
    they are not decoded into positions here).
    """
    if len(body) < 26:
        raise ValueError("0xC0 state body is too short")
    mode_value = (body[2] >> 4) & 0x7
    run_mode = body[2] & 0xF
    fan_value = body[3] & 0x7F
    power_on = bool(body[1] & 0x01)
    return {
        "power": power_on,
        "mode": mode_value,
        "modeName": AC_MODE_NAME_BY_VALUE.get(mode_value, "unknown"),
        "runMode": run_mode,
        "runModeName": AC_RUN_MODE_NAMES.get(run_mode, "unknown") if power_on else "off",
        "fanSpeed": fan_value,
        "fanName": AC_FAN_NAME_BY_VALUE.get(fan_value, "unknown"),
        "targetTemperature": (body[4] & 0x7F) / 2,
        "targetTemperatureFlag": bool(body[4] & 0x80),
        "indoorTemperature": decode_ac_temperature(body[13], body[15] & 0x0F),
        # Matches property 0x05. 0xFF while the unit is off / sensor idle.
        "outdoorTemperature": decode_ac_temperature(body[14], body[15] >> 4),
        # Always about 1.5C below the indoor value on this unit; likely the
        # indoor coil. Kept raw because the meaning is not confirmed.
        "coilTemperature": decode_ac_temperature(body[12], body[15] >> 4),
        "humidity": body[10],
        # Swing state flags; they mirror properties 0x08 / 0x09.
        "swingUDActive": bool(body[11] & 0x10),
        "swingLRActive": bool(body[11] & 0x01),
        # Louver/sweep related, encoding not confirmed.
        "louverUDRaw": body[19],
        "louverLRRaw": body[20],
        "eco": bool(body[16] & 0x01),
        "purifier": bool(body[16] & 0x02),
        # 0x7F means "not set".
        "onTimer": body[5],
        "offTimer": body[7],
        "rawHex": body.hex().upper(),
    }


class IoLifeClient:
    def __init__(
        self,
        host: str = HOST,
        scheme: str = SCHEME,
        server_version: str = SERVER_VERSION,
        app_id: str = APP_ID,
        app_key: str = APP_KEY,
        app_src: str = APP_SRC,
        client_type: str = CLIENT_TYPE,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self.host = host
        self.scheme = scheme
        self.server_version = server_version
        self.app_id = app_id
        self.app_key = app_key
        self.app_src = app_src
        self.client_type = client_type
        self.language = language

    def _request_path(self, endpoint: str) -> str:
        endpoint = endpoint.lstrip("/")
        return f"/{self.server_version}/{endpoint}"

    def _base_params(self, session_id: Optional[str] = None) -> Dict[str, str]:
        params: Dict[str, str] = {
            "format": "2",
            "stamp": now_stamp(),
            "language": self.language,
            "appId": self.app_id,
            "src": self.app_src,
        }
        if session_id:
            params["sessionId"] = session_id
        return params

    def _sign(self, path: str, params: Dict[str, Any]) -> str:
        items = sorted((k, str(v)) for k, v in params.items())
        payload = "&".join(f"{k}={v}" for k, v in items)
        source = f"{path}{payload}{self.app_key}"
        return sha256_hex(source)

    def _post(self, endpoint: str, params: Dict[str, Any], signed: bool = True) -> Dict[str, Any]:
        path = self._request_path(endpoint)
        payload: Dict[str, Any] = dict(params)
        if signed:
            payload["sign"] = self._sign(path, payload)
        body = urllib.parse.urlencode(payload).encode("utf-8")
        url = f"{self.scheme}://{self.host}{path}"
        req = urllib.request.Request(url=url, data=body, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")
            if exc.code == 504:
                hint = (
                    "Gateway timeout: cloud API is reachable, but appliance response timed out. "
                    "This is usually caused by an offline device, wrong appliance-id, or invalid payload."
                )
                raise RuntimeError(f"HTTP 504: {err}\nHint: {hint}") from exc
            raise RuntimeError(f"HTTP {exc.code}: {err}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"network error: {exc}") from exc
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"invalid JSON response: {text}") from None

    @staticmethod
    def _require_success(resp: Dict[str, Any]) -> Dict[str, Any]:
        error_code = str(resp.get("errorCode", "")).strip()
        if error_code != "0":
            raise RuntimeError(f"API error: errorCode={error_code}, msg={resp.get('msg')}, raw={resp}")
        return resp

    def get_login_id(self, account: str) -> str:
        params = self._base_params()
        params["clientType"] = self.client_type
        params["loginAccount"] = account
        resp = self._require_success(self._post("user/login/id/get", params, signed=True))
        result = resp.get("result") or {}
        login_id = result.get("loginId")
        if not login_id:
            raise RuntimeError(f"loginId not found in response: {resp}")
        return str(login_id)

    def login(self, account: str, password: str, push_type: str = "4", push_token: str = "false") -> Dict[str, Any]:
        login_id = self.get_login_id(account)
        password_sha = sha256_hex(password)
        password_enc = sha256_hex(f"{login_id}{password_sha}{self.app_key}")
        iampwd = sha256_hex(f"{login_id}{md5_hex(md5_hex(password))}{self.app_key}")

        params = self._base_params()
        params["clientType"] = self.client_type
        params["loginAccount"] = account
        params["password"] = password_enc
        params["pushType"] = push_type
        params["pushToken"] = push_token
        params["iampwd"] = iampwd

        resp = self._require_success(self._post("user/login", params, signed=True))
        result = resp.get("result") or {}

        access_token = result.get("accessToken")
        random_data = result.get("randomData")
        data_key = None
        data_iv = None
        if access_token:
            try:
                data_key = decode_with_app_key(str(access_token), self.app_key)
            except Exception:
                data_key = None
        if random_data:
            try:
                data_iv = decode_with_app_key(str(random_data), self.app_key)
            except Exception:
                data_iv = None

        return {
            "account": account,
            "loginId": login_id,
            "sessionId": result.get("sessionId"),
            "userId": result.get("userId"),
            "accessToken": access_token,
            "randomData": random_data,
            "dataKey": data_key,
            "dataIV": data_iv,
            "raw": resp,
        }

    def list_devices(self, session_id: str, app_version: str = DEFAULT_APP_VERSION) -> Dict[str, Any]:
        params = self._base_params(session_id=session_id)
        params["appVersion"] = app_version
        params["clientType"] = self.client_type
        params["appId"] = self.app_id
        return self._post("appliance/user/home/page/list/info", params, signed=True)

    def transparent_send(self, session_id: str, appliance_id: str, order: str) -> Dict[str, Any]:
        params = self._base_params(session_id=session_id)
        params["applianceId"] = appliance_id
        params["funId"] = APP_ENTERPRISE
        params["order"] = order
        return self._post("appliance/transparent/send", params, signed=True)

    def call(self, endpoint: str, params: Dict[str, str], session_id: Optional[str]) -> Dict[str, Any]:
        merged = self._base_params(session_id=session_id)
        merged.update(params)
        return self._post(endpoint, merged, signed=True)


def load_session(path: pathlib.Path = SESSION_FILE) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"session file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(data: Dict[str, Any], path: pathlib.Path = SESSION_FILE) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_kv(items: List[str]) -> Dict[str, str]:
    params: Dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"invalid --param '{item}', expected key=value")
        key, value = item.split("=", 1)
        params[key] = value
    return params


def resolve_session_and_session_id(session_id_arg: Optional[str]) -> Tuple[Dict[str, Any], str]:
    session = load_session()
    session_id = session_id_arg or session.get("sessionId")
    if not session_id:
        raise RuntimeError("sessionId not found. Run login first.")
    return session, str(session_id)


def build_order_from_payload(
    session: Dict[str, Any],
    payload_hex: str,
    appliance_id: str,
    msg_type: int = 32,
    msg_id: Optional[int] = None,
    verbose: bool = False,
) -> str:
    data_key = session.get("dataKey")
    if not data_key:
        raise RuntimeError("dataKey missing in session; transparent encode is not available")
    data_iv = session.get("dataIV")
    normalized_payload = payload_hex.strip().replace(" ", "").replace(":", "")
    packet = build_wifidatagram(
        payload_hex=normalized_payload,
        appliance_id=appliance_id,
        msg_type=msg_type,
        msg_id=msg_id,
    )
    plain_dec = bytes_to_dec_string(packet)
    order = aes_encrypt_hex(plain_dec, data_key, data_iv if data_iv else None)
    if verbose:
        print("payload-hex:", normalized_payload.upper())
        print("plain-dec:", plain_dec)
        print("packet-hex:", packet.hex().upper())
        print("order:", order)
    return order


def decode_transparent_reply(
    session: Dict[str, Any],
    resp: Dict[str, Any],
) -> Optional[bytes]:
    """Decrypt a reply and return the AC body (without the 16-byte UART header/CRC)."""
    if str(resp.get("errorCode", "")).strip() != "0":
        return None
    reply = (resp.get("result") or {}).get("reply")
    data_key = session.get("dataKey")
    if not reply or not data_key:
        return None
    dec = aes_decrypt_hex(str(reply), data_key, session.get("dataIV") or None)
    frame = dec_string_to_bytes(dec)
    parsed = parse_wifidatagram(frame)
    inner = bytes.fromhex(parsed["bodyHex"])
    if len(inner) < 18:
        return None
    body_length = int.from_bytes(inner[4:6], "little") + 4 - 18
    if body_length < 0:
        return None
    return inner[16 : 16 + body_length]


def decode_transparent_reply_if_requested(
    session: Dict[str, Any],
    resp: Dict[str, Any],
    decode_reply: bool,
) -> None:
    if not decode_reply:
        return
    if str(resp.get("errorCode", "")).strip() != "0":
        return
    result = resp.get("result") or {}
    reply = result.get("reply")
    data_key = session.get("dataKey")
    if reply and data_key:
        data_iv = session.get("dataIV")
        dec = aes_decrypt_hex(str(reply), data_key, data_iv if data_iv else None)
        raw = dec_string_to_bytes(dec)
        try:
            parsed = parse_wifidatagram(raw)
            print(json.dumps({"replyDec": dec, "replyParsed": parsed}, ensure_ascii=False, indent=2))
        except Exception as exc:
            print(json.dumps({"replyDec": dec, "replyHex": raw.hex().upper(), "replyParseError": str(exc)}, ensure_ascii=False, indent=2))


def send_transparent_order(
    language: str,
    session_id: str,
    appliance_id: str,
    order: str,
) -> Dict[str, Any]:
    client = IoLifeClient(language=language)
    resp = client.transparent_send(session_id=session_id, appliance_id=appliance_id, order=order)
    print(json.dumps(resp, ensure_ascii=False, indent=2))
    return resp


def cmd_login(args: argparse.Namespace) -> None:
    client = IoLifeClient(language=args.language)
    session = client.login(account=args.account, password=args.password, push_type=args.push_type, push_token=args.push_token)
    save_session(session)
    print(f"saved: {SESSION_FILE}")
    print(json.dumps({k: session.get(k) for k in ['account', 'userId', 'sessionId', 'dataKey', 'dataIV']}, ensure_ascii=False, indent=2))


def cmd_devices(args: argparse.Namespace) -> None:
    session = load_session()
    session_id = args.session_id or session.get("sessionId")
    if not session_id:
        raise RuntimeError("sessionId not found. Run login first.")
    client = IoLifeClient(language=args.language)
    resp = client.list_devices(session_id=session_id, app_version=args.app_version)
    print(json.dumps(resp, ensure_ascii=False, indent=2))


def cmd_call(args: argparse.Namespace) -> None:
    params = parse_kv(args.param or [])
    session_id = args.session_id
    if args.use_saved_session:
        session = load_session()
        session_id = session_id or session.get("sessionId")
    client = IoLifeClient(language=args.language)
    resp = client.call(endpoint=args.endpoint, params=params, session_id=session_id)
    print(json.dumps(resp, ensure_ascii=False, indent=2))


def cmd_transparent(args: argparse.Namespace) -> None:
    session, session_id = resolve_session_and_session_id(args.session_id)

    order = args.order
    if not order:
        payload_hex = args.payload_hex
        if not payload_hex:
            raise RuntimeError("either --order or --payload-hex is required")
        order = build_order_from_payload(
            session=session,
            payload_hex=payload_hex,
            appliance_id=args.appliance_id,
            msg_type=args.msg_type,
            msg_id=args.msg_id,
            verbose=args.verbose,
        )

    resp = send_transparent_order(
        language=args.language,
        session_id=session_id,
        appliance_id=args.appliance_id,
        order=order,
    )
    decode_transparent_reply_if_requested(session=session, resp=resp, decode_reply=args.decode_reply)


def cmd_ac_query(args: argparse.Namespace) -> None:
    all_props = args.query_type == "all_props"
    if all_props:
        payload = build_ac_query_properties_payload(AC_ALL_PROPERTIES).hex().upper()
    else:
        payload = build_ac_query_payload(query_type=args.query_type).hex().upper()
    if args.print_payload:
        print(payload)
        return

    session, session_id = resolve_session_and_session_id(args.session_id)
    order = build_order_from_payload(
        session=session,
        payload_hex=payload,
        appliance_id=args.appliance_id,
        msg_type=args.msg_type,
        msg_id=args.msg_id,
        verbose=args.verbose,
    )
    resp = send_transparent_order(
        language=args.language,
        session_id=session_id,
        appliance_id=args.appliance_id,
        order=order,
    )
    decode_transparent_reply_if_requested(session=session, resp=resp, decode_reply=args.decode_reply)

    if not args.decode:
        return
    body = decode_transparent_reply(session=session, resp=resp)
    if body is None:
        print(json.dumps({"decodeError": "reply could not be decoded"}, ensure_ascii=False))
        return
    try:
        if body[0] in (AC_RESPONSE_ID_PROPERTIES, AC_RESPONSE_ID_PROPERTIES_ACK):
            decoded: Any = {"properties": parse_ac_properties_response(body)}
        elif body[0] == AC_RESPONSE_ID_STATE:
            decoded = {"state": decode_ac_state_body(body)}
        else:
            decoded = {"unknown": body.hex().upper()}
    except Exception as exc:
        decoded = {"decodeError": str(exc), "bodyHex": body.hex().upper()}
    print(json.dumps(decoded, ensure_ascii=False, indent=2))


def cmd_ac_power(args: argparse.Namespace) -> None:
    state_value = 1 if args.state.lower() == "on" else 0
    if args.batch:
        payload = build_ac_set_properties_payload([(0x01, [state_value])])
    else:
        payload = build_ac_power_payload(state=args.state)
    if args.print_payload:
        print(payload.hex().upper())
        return

    session, session_id = resolve_session_and_session_id(args.session_id)
    order = build_order_from_payload(
        session=session,
        payload_hex=payload,
        appliance_id=args.appliance_id,
        msg_type=args.msg_type,
        msg_id=args.msg_id,
        verbose=args.verbose,
    )
    resp = send_transparent_order(
        language=args.language,
        session_id=session_id,
        appliance_id=args.appliance_id,
        order=order,
    )
    decode_transparent_reply_if_requested(session=session, resp=resp, decode_reply=args.decode_reply)


def build_ac_control_settings(
    mode: Optional[str] = None,
    temperature: Optional[float] = None,
    fan: Optional[str] = None,
) -> List[Tuple[int, List[int]]]:
    settings: List[Tuple[int, List[int]]] = []
    if mode is not None:
        key = mode.strip().lower()
        if key not in AC_OPERATION_MODES:
            supported = ", ".join(AC_OPERATION_MODES.keys())
            raise ValueError(f"unsupported --mode '{mode}'. use: {supported}")
        settings.append((0x02, [AC_OPERATION_MODES[key]]))
    if temperature is not None:
        if not AC_TEMPERATURE_MIN <= temperature <= AC_TEMPERATURE_MAX:
            raise ValueError(
                f"--temperature must be between {AC_TEMPERATURE_MIN} and {AC_TEMPERATURE_MAX}"
            )
        # The wire format uses 0.5C steps: 24C -> 0x30, 30C -> 0x3C.
        settings.append((0x03, [int(round(temperature * 2))]))
    if fan is not None:
        key = fan.strip().lower()
        if key not in AC_FAN_SPEEDS:
            supported = ", ".join(AC_FAN_SPEEDS.keys())
            raise ValueError(f"unsupported --fan '{fan}'. use: {supported}")
        settings.append((0x06, [AC_FAN_SPEEDS[key]]))
    return settings


def cmd_ac_control(args: argparse.Namespace) -> None:
    if args.mode is None and args.temperature is None and args.fan is None:
        raise RuntimeError("at least one of --mode/--temperature/--fan is required")

    settings = build_ac_control_settings(args.mode, args.temperature, args.fan)
    if args.print_payload:
        if args.batch:
            print(build_ac_set_properties_payload(settings).hex().upper())
        else:
            for prop_code, raw in settings:
                print(build_ac_control_payload(prop_code, raw).hex().upper())
        return

    session, session_id = resolve_session_and_session_id(args.session_id)
    # --batch sends every setting in one frame, so the AC beeps only once.
    payloads = (
        [build_ac_set_properties_payload(settings)]
        if args.batch
        else [build_ac_control_payload(prop_code, raw) for prop_code, raw in settings]
    )
    for payload in payloads:
        order = build_order_from_payload(
            session=session,
            payload_hex=payload.hex().upper(),
            appliance_id=args.appliance_id,
            msg_type=args.msg_type,
            msg_id=args.msg_id,
            verbose=args.verbose,
        )
        resp = send_transparent_order(
            language=args.language,
            session_id=session_id,
            appliance_id=args.appliance_id,
            order=order,
        )
        decode_transparent_reply_if_requested(session=session, resp=resp, decode_reply=args.decode_reply)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IoLIFE (Toshiba/Midea) API helper")
    parser.add_argument("--language", default=DEFAULT_LANGUAGE, help="request language (default: ja_JP)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="login and save session")
    p_login.add_argument("--account", required=True, help="loginAccount (email)")
    p_login.add_argument("--password", required=True, help="raw password")
    p_login.add_argument("--push-type", default="4")
    p_login.add_argument("--push-token", default="false")
    p_login.set_defaults(func=cmd_login)

    p_dev = sub.add_parser("devices", help="list devices")
    p_dev.add_argument("--session-id")
    p_dev.add_argument("--app-version", default=DEFAULT_APP_VERSION)
    p_dev.set_defaults(func=cmd_devices)

    p_call = sub.add_parser("call", help="generic signed API call")
    p_call.add_argument("--endpoint", required=True, help="e.g. user/info/get")
    p_call.add_argument("--param", action="append", help="key=value", default=[])
    p_call.add_argument("--session-id")
    p_call.add_argument("--use-saved-session", action="store_true")
    p_call.set_defaults(func=cmd_call)

    p_trans = sub.add_parser("transparent", help="call appliance/transparent/send")
    p_trans.add_argument("--appliance-id", required=True)
    p_trans.add_argument("--order", help="already encrypted order string")
    p_trans.add_argument("--payload-hex", help="raw payload hex; script builds datagram and encrypts")
    p_trans.add_argument("--msg-type", type=int, default=32)
    p_trans.add_argument("--msg-id", type=int)
    p_trans.add_argument("--session-id")
    p_trans.add_argument("--decode-reply", action="store_true")
    p_trans.add_argument("--verbose", action="store_true")
    p_trans.set_defaults(func=cmd_transparent)

    p_ac_query = sub.add_parser("ac-query", help="AC(0xAC) query payload builder + transparent send")
    p_ac_query.add_argument("--appliance-id", required=True)
    p_ac_query.add_argument("--query-type", default="all", help="all, all_props, or one property key (e.g. power/mode/temperature)")
    p_ac_query.add_argument("--decode", action="store_true", help="decode the AC body into readable fields")
    p_ac_query.add_argument("--print-payload", action="store_true", help="print payload hex and exit")
    p_ac_query.add_argument("--msg-type", type=int, default=32)
    p_ac_query.add_argument("--msg-id", type=int)
    p_ac_query.add_argument("--session-id")
    p_ac_query.add_argument("--decode-reply", action="store_true")
    p_ac_query.add_argument("--verbose", action="store_true")
    p_ac_query.set_defaults(func=cmd_ac_query)

    p_ac_power = sub.add_parser("ac-power", help="AC(0xAC) power control + transparent send")
    p_ac_power.add_argument("--appliance-id", required=True)
    p_ac_power.add_argument("--state", required=True, choices=["on", "off"])
    p_ac_power.add_argument("--batch", action="store_true", help="send a multi-property (B0) frame instead")
    p_ac_power.add_argument("--print-payload", action="store_true", help="print payload hex and exit")
    p_ac_power.add_argument("--msg-type", type=int, default=32)
    p_ac_power.add_argument("--msg-id", type=int)
    p_ac_power.add_argument("--session-id")
    p_ac_power.add_argument("--decode-reply", action="store_true")
    p_ac_power.add_argument("--verbose", action="store_true")
    p_ac_power.set_defaults(func=cmd_ac_power)

    p_ac_control = sub.add_parser("ac-control", help="AC(0xAC) mode/temperature/fan control + transparent send")
    p_ac_control.add_argument("--appliance-id", required=True)
    p_ac_control.add_argument("--mode", choices=list(AC_OPERATION_MODES.keys()))
    p_ac_control.add_argument("--temperature", type=float, help="target temperature (16-32, 0.5C steps)")
    p_ac_control.add_argument("--fan", choices=list(AC_FAN_SPEEDS.keys()), help="fan speed")
    p_ac_control.add_argument("--batch", action="store_true", help="send one multi-property (B0) frame (single beep)")
    p_ac_control.add_argument("--print-payload", action="store_true", help="print payload hex and exit")
    p_ac_control.add_argument("--msg-type", type=int, default=32)
    p_ac_control.add_argument("--msg-id", type=int)
    p_ac_control.add_argument("--session-id")
    p_ac_control.add_argument("--decode-reply", action="store_true")
    p_ac_control.add_argument("--verbose", action="store_true")
    p_ac_control.set_defaults(func=cmd_ac_control)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
