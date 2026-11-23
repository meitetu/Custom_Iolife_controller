"""Async client and AC protocol helpers for the Toshiba IoLIFE cloud API.

This is a port of the protocol logic verified in ``main.py``. Only the commands
that were confirmed against a real unit (RAS-G221E8P(W)) are exposed:

   0x01 power / 0x02 mode / 0x03 target temperature / 0x06 fan speed
   0x08 swing UD / 0x09 swing LR / 0x0D eco / 0x0E purifier

Writes use a single multi-property (``B0``) frame so the unit beeps once.
See ``Iolife_API_SPEC.md`` for the byte layout and the verification notes.

The module deliberately has no Home Assistant imports so it can be tested
standalone.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
from Crypto.Cipher import AES

HOST = "app.iolife.toshiba-lifestyle.com"
SERVER_VERSION = "v1"
APP_ID = "1203"
APP_KEY = "09c4d09f0da1513bb62dc7b6b0af9c11"
APP_SRC = "203"
CLIENT_TYPE = "1"
APP_ENTERPRISE = "0008"
DEFAULT_LANGUAGE = "ja_JP"
DEFAULT_APP_VERSION = "3.3.2"
REQUEST_TIMEOUT = 25

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
    "auto": 0x66,
    "strong": 0x50,
    "mid": 0x3C,
    "weak": 0x14,
    "mute": 0x01,
}
AC_FAN_NAME_BY_VALUE: Dict[int, str] = {v: k for k, v in AC_FAN_SPEEDS.items()}
AC_MODE_NAME_BY_VALUE: Dict[int, str] = {v: k for k, v in AC_OPERATION_MODES.items()}

# Measured on RAS-G221E8P(W): 0x20 (16.0C) .. 0x3C (30.0C).
# 0x3D and above are acknowledged but silently ignored.
AC_TEMPERATURE_MIN = 16.0
AC_TEMPERATURE_MAX = 30.0
AC_TEMPERATURE_STEP = 0.5

# Properties polled together in one B1 query.
AC_ALL_PROPERTIES: List[int] = [
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
    0x0D, 0x0E, 0x15, 0x17, 0x3F,
]
# Property ids for convenience.
PROP_POWER = 0x01
PROP_MODE = 0x02
PROP_TARGET_TEMP = 0x03
PROP_INDOOR_TEMP = 0x04
PROP_OUTDOOR_TEMP = 0x05
PROP_FAN = 0x06
PROP_SWING_UD = 0x08
PROP_SWING_LR = 0x09
PROP_ECO = 0x0D
PROP_PURIFIER = 0x0E
PROP_HUMIDITY = 0x15
PROP_SCREEN = 0x17
PROP_ERROR_CODE = 0x3F

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

# Message ids are sequential per process, as in the reference implementation.
_MESSAGE_COUNTER = itertools.count(1)


class IolifeError(Exception):
    """Base error for the IoLIFE client."""


class IolifeAuthError(IolifeError):
    """Raised when credentials are rejected or the session expired."""


class IolifeConnectionError(IolifeError):
    """Raised when the cloud or appliance cannot be reached."""


class IolifeTimeoutError(IolifeConnectionError):
    """Raised when the cloud reports HTTP 504 (the appliance did not answer)."""


@dataclass
class IolifeSession:
    """Authenticated session state."""

    login_id: str
    session_id: str
    user_id: str
    data_key: str
    data_iv: Optional[str] = None


# --------------------------------------------------------------------------- #
# Crypto helpers
# --------------------------------------------------------------------------- #
def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().lower()


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().lower()


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len]) * pad_len


def _pkcs7_unpad(data: bytes, block_size: int = 16) -> bytes:
    if not data or len(data) % block_size != 0:
        raise ValueError("invalid AES block data")
    pad_len = data[-1]
    if pad_len <= 0 or pad_len > block_size:
        raise ValueError("invalid PKCS7 padding")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("invalid PKCS7 padding bytes")
    return data[:-pad_len]


def aes_encrypt_hex(plain_text: str, key_text: str, iv_text: Optional[str] = None) -> str:
    key = key_text.encode("utf-8")
    data = _pkcs7_pad(plain_text.encode("utf-8"))
    if iv_text:
        cipher = AES.new(key, AES.MODE_CBC, iv_text.encode("utf-8"))
    else:
        cipher = AES.new(key, AES.MODE_ECB)
    return cipher.encrypt(data).hex()


def aes_decrypt_hex(cipher_hex: str, key_text: str, iv_text: Optional[str] = None) -> str:
    key = key_text.encode("utf-8")
    raw = bytes.fromhex(cipher_hex)
    if iv_text:
        cipher = AES.new(key, AES.MODE_CBC, iv_text.encode("utf-8"))
    else:
        cipher = AES.new(key, AES.MODE_ECB)
    return _pkcs7_unpad(cipher.decrypt(raw)).decode("utf-8")


def _app_key_crypto_key() -> str:
    return md5_hex(APP_KEY)[:16]


def decode_with_app_key(cipher_hex: str) -> str:
    """Decrypt a login field (accessToken / randomData)."""
    return aes_decrypt_hex(cipher_hex, _app_key_crypto_key(), None)


# --------------------------------------------------------------------------- #
# Frame helpers
# --------------------------------------------------------------------------- #
def _now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d%H%M%S")


def _signed_byte(value: int) -> int:
    return value - 256 if value > 127 else value


def _bytes_to_dec_string(data: bytes) -> str:
    return ",".join(str(_signed_byte(b)) for b in data)


def _dec_string_to_bytes(data: str) -> bytes:
    values: List[int] = []
    for part in data.split(","):
        part = part.strip()
        if not part:
            continue
        values.append((int(part) + 256) % 256)
    return bytes(values)


def _timestamp_bytes() -> bytes:
    now = dt.datetime.now()
    return bytes(
        [
            (now.microsecond // 1000) & 0xFF,
            now.second & 0xFF,
            now.minute & 0xFF,
            (now.hour % 12) & 0xFF,
            now.day & 0xFF,
            (now.month - 1) & 0xFF,
            (now.year % 100) & 0xFF,
            (now.year // 100) & 0xFF,
        ]
    )


def build_wifidatagram(payload_hex: str, appliance_id: str) -> bytes:
    body = bytes.fromhex(payload_hex)
    dev_id = int(appliance_id).to_bytes(8, "little", signed=False)[:6]
    length = len(body) + 56
    packet = bytearray(b"\x5A\x5A\x01\x00")
    packet += length.to_bytes(2, "little")
    packet += (32).to_bytes(2, "little")
    packet += next(_MESSAGE_COUNTER).to_bytes(4, "little")
    packet += _timestamp_bytes()
    packet += dev_id
    packet += b"\x00\x00"
    packet += bytes(6)
    packet += bytes(6)
    packet += body
    packet += bytes(16)
    if len(packet) != length:
        raise ValueError(f"datagram length mismatch: {len(packet)} != {length}")
    return bytes(packet)


def parse_wifidatagram(data: bytes) -> Dict[str, Any]:
    if len(data) < 56 or data[0:2] != b"\x5A\x5A":
        raise ValueError("invalid datagram")
    length = int.from_bytes(data[4:6], "little")
    body_len = length - 56
    return {
        "length": length,
        "msgType": int.from_bytes(data[6:8], "little"),
        "msgId": int.from_bytes(data[8:12], "little"),
        "body": data[40 : 40 + body_len] if body_len > 0 else b"",
    }


def crc16_ccitt(data: List[int], start_pos: int, end_pos: int) -> int:
    crc = 0
    for si in range(start_pos, end_pos + 1):
        crc ^= data[si] << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def crc8_854(data: List[int], start_pos: int, end_pos: int) -> int:
    crc = 0
    for si in range(start_pos, end_pos + 1):
        crc = CRC8_854_TABLE[(crc ^ data[si]) & 0xFF]
    return crc


def build_ac_uart_payload(body: List[int], request_type: int) -> bytes:
    msg_length = len(body) + 0x10 + 2
    msg = [0] * msg_length
    msg[0:4] = [0x55, 0xAA, 0xCC, 0x33]
    msg_len = msg_length - 4
    msg[4] = msg_len & 0xFF
    msg[5] = (msg_len >> 8) & 0xFF
    msg[6] = 0x01
    msg[7] = AC_DEVICE_TYPE
    msg[14] = request_type & 0xFF
    msg[15] = (request_type >> 8) & 0xFF
    for index, value in enumerate(body):
        msg[0x10 + index] = value & 0xFF
    crc = crc16_ccitt(msg, 0, msg_length - 3)
    msg[msg_length - 2] = crc & 0xFF
    msg[msg_length - 1] = (crc >> 8) & 0xFF
    return bytes(msg)


# --------------------------------------------------------------------------- #
# AC payload builders
# --------------------------------------------------------------------------- #
def _finish_body(body: List[int]) -> List[int]:
    body.append(random.randint(1, 254))
    body.append(0x00)
    body[-1] = crc8_854(body, 0, len(body) - 2)
    return body


def build_ac_query_properties_payload(prop_codes: List[int]) -> bytes:
    body = [AC_QUERY_PROPERTY_CMD, len(prop_codes)]
    for prop_code in prop_codes:
        body.extend([prop_code & 0xFF, (prop_code >> 8) & 0xFF])
    return build_ac_uart_payload(_finish_body(body), AC_REQUEST_QUERY)


def build_ac_set_properties_payload(settings: List[Tuple[int, List[int]]]) -> bytes:
    """Build a B0 frame. Several settings at once means a single beep."""
    body = [AC_CONTROL_PROPERTY_CMD, len(settings)]
    for prop_code, raw in settings:
        body.extend([prop_code & 0xFF, (prop_code >> 8) & 0xFF, len(raw)])
        body.extend(value & 0xFF for value in raw)
    return build_ac_uart_payload(_finish_body(body), AC_REQUEST_CONTROL)


# --------------------------------------------------------------------------- #
# Property decoding
# --------------------------------------------------------------------------- #
def decode_ac_temperature(raw_base: int, decimals: int) -> Optional[float]:
    """Decode temperatures: (raw - 50) / 2 plus the decimal nibble."""
    if raw_base == 0xFF:
        return None
    base = (raw_base - 50) / 2
    fraction = decimals / 10
    return round(base + (fraction if base >= 0 else -fraction), 1)


def parse_ac_properties_response(body: bytes) -> Dict[int, Any]:
    """Parse a B1 TLV reply into ``{property: value}``."""
    if len(body) < 2:
        raise ValueError("property response body is too short")
    count = body[1]
    cursor = 2
    values: Dict[int, Any] = {}
    for _ in range(count):
        if len(body) - cursor < 4:
            break
        prop_code = int.from_bytes(body[cursor : cursor + 2], "little")
        size = body[cursor + 3]
        raw = body[cursor + 4 : cursor + 4 + size]
        cursor += 4 + size
        if not raw:
            values[prop_code] = None
            continue
        if prop_code in (PROP_INDOOR_TEMP, PROP_OUTDOOR_TEMP) and len(raw) >= 2:
            values[prop_code] = decode_ac_temperature(raw[0], raw[1])
        elif prop_code == PROP_TARGET_TEMP:
            values[prop_code] = raw[0] / 2
        elif prop_code == PROP_FAN:
            values[prop_code] = AC_FAN_NAME_BY_VALUE.get(raw[0], f"0x{raw[0]:02X}")
        elif prop_code == PROP_MODE:
            values[prop_code] = AC_MODE_NAME_BY_VALUE.get(raw[0], "unknown")
        elif prop_code in (PROP_SWING_UD, PROP_SWING_LR, PROP_ECO, PROP_PURIFIER):
            values[prop_code] = bool(raw[0])
        else:
            values[prop_code] = raw[0]
    return values


# --------------------------------------------------------------------------- #
# Cloud client
# --------------------------------------------------------------------------- #
class IolifeClient:
    """Minimal async client for the IoLIFE cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        language: str = DEFAULT_LANGUAGE,
    ) -> None:
        self._http = session
        self._email = email
        self._password = password
        self._language = language
        self.session: Optional[IolifeSession] = None

    # -- low level ---------------------------------------------------------
    def _sign(self, path: str, params: Dict[str, Any]) -> str:
        payload = "&".join(f"{k}={v}" for k, v in sorted((k, str(v)) for k, v in params.items()))
        return sha256_hex(f"{path}{payload}{APP_KEY}")

    async def _post(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        path = f"/{SERVER_VERSION}/{endpoint.lstrip('/')}"
        payload = dict(params)
        payload["sign"] = self._sign(path, payload)
        try:
            async with self._http.post(
                f"https://{HOST}{path}",
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                text = await response.text()
        except aiohttp.ClientError as err:
            raise IolifeConnectionError(f"network error: {err}") from err
        except TimeoutError as err:
            raise IolifeConnectionError("request timed out") from err

        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            raise IolifeError(f"invalid JSON response: {text[:200]}") from err

        error_code = str(data.get("errorCode", "")).strip()
        if error_code in ("3106", "3107") or data.get("message") == "invalidSession":
            raise IolifeAuthError(f"session expired (errorCode={error_code})")
        if error_code != "0":
            raise IolifeError(f"API error: errorCode={error_code}, msg={data.get('msg')}")
        return data

    def _base_params(self, session_id: Optional[str] = None) -> Dict[str, str]:
        params = {
            "format": "2",
            "stamp": _now_stamp(),
            "language": self._language,
            "appId": APP_ID,
            "src": APP_SRC,
        }
        if session_id:
            params["sessionId"] = session_id
        return params

    # -- auth --------------------------------------------------------------
    async def async_login(self) -> IolifeSession:
        params = self._base_params()
        params["clientType"] = CLIENT_TYPE
        params["loginAccount"] = self._email
        result = (await self._post("user/login/id/get", params)).get("result") or {}
        login_id = result.get("loginId")
        if not login_id:
            raise IolifeAuthError("loginId not found in response")

        params = self._base_params()
        params["clientType"] = CLIENT_TYPE
        params["loginAccount"] = self._email
        params["password"] = sha256_hex(f"{login_id}{sha256_hex(self._password)}{APP_KEY}")
        params["iampwd"] = sha256_hex(
            f"{login_id}{md5_hex(md5_hex(self._password))}{APP_KEY}"
        )
        params["pushType"] = "4"
        params["pushToken"] = "false"
        result = (await self._post("user/login", params)).get("result") or {}

        access_token = result.get("accessToken")
        if not access_token:
            raise IolifeAuthError("login failed: no accessToken")
        random_data = result.get("randomData")

        self.session = IolifeSession(
            login_id=str(login_id),
            session_id=str(result.get("sessionId")),
            user_id=str(result.get("userId")),
            data_key=decode_with_app_key(str(access_token)),
            data_iv=decode_with_app_key(str(random_data)) if random_data else None,
        )
        return self.session

    def _require_session(self) -> IolifeSession:
        if self.session is None:
            raise IolifeAuthError("not logged in")
        return self.session

    # -- devices -----------------------------------------------------------
    async def async_list_devices(self) -> List[Dict[str, Any]]:
        params = self._base_params(self._require_session().session_id)
        params["appVersion"] = DEFAULT_APP_VERSION
        params["clientType"] = CLIENT_TYPE
        params["appId"] = APP_ID
        data = await self._post("appliance/user/home/page/list/info", params)
        return list(data.get("result") or [])

    # -- appliance I/O -----------------------------------------------------
    def _build_order(self, payload: bytes, appliance_id: str) -> str:
        session = self._require_session()
        packet = build_wifidatagram(payload.hex(), appliance_id)
        return aes_encrypt_hex(
            _bytes_to_dec_string(packet), session.data_key, session.data_iv or None
        )

    def _decode_reply(self, reply: str) -> Optional[bytes]:
        session = self._require_session()
        plain = aes_decrypt_hex(reply, session.data_key, session.data_iv or None)
        frame = _dec_string_to_bytes(plain)
        parsed = parse_wifidatagram(frame)
        inner = parsed["body"]
        if len(inner) < 18 or inner[0:4] != b"\x55\xAA\xCC\x33":
            raise IolifeError("unexpected reply frame")
        body_len = int.from_bytes(inner[4:6], "little") + 4 - 18
        return inner[16 : 16 + body_len]

    async def _async_send(self, appliance_id: str, payload: bytes) -> Optional[bytes]:
        params = self._base_params(self._require_session().session_id)
        params["applianceId"] = appliance_id
        params["funId"] = APP_ENTERPRISE
        params["order"] = self._build_order(payload, appliance_id)
        try:
            data = await self._post("appliance/transparent/send", params)
        except IolifeError as err:
            if "504" in str(err):
                raise IolifeTimeoutError(
                    "the cloud timed out waiting for the appliance; "
                    "check it is online and the appliance id is correct"
                ) from err
            raise
        reply = (data.get("result") or {}).get("reply")
        if not reply:
            return None
        return self._decode_reply(str(reply))

    async def async_query_properties(
        self, appliance_id: str, prop_codes: Optional[List[int]] = None
    ) -> Dict[int, Any]:
        """Query many properties at once (no beep)."""
        payload = build_ac_query_properties_payload(prop_codes or AC_ALL_PROPERTIES)
        body = await self._async_send(appliance_id, payload)
        if body is None:
            return {}
        return parse_ac_properties_response(body)

    async def async_set_properties(
        self, appliance_id: str, settings: List[Tuple[int, List[int]]]
    ) -> None:
        """Apply several settings in one frame, so the unit beeps only once."""
        if not settings:
            return
        payload = build_ac_set_properties_payload(settings)
        await self._async_send(appliance_id, payload)
