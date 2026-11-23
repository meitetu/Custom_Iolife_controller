"""Tests for the IoLIFE protocol helpers. No network access."""
from custom_components.iolife import api


def test_temperature_decode_matches_captures():
    # Verified against RAS-G221E8P(W) captures.
    assert api.decode_ac_temperature(0x64, 0) == 25.0
    assert api.decode_ac_temperature(0x4C, 6) == 13.6
    assert api.decode_ac_temperature(0x62, 3) == 24.3
    assert api.decode_ac_temperature(0xFF, 0) is None


def _reply_body(entries):
    """Build a B1 reply body: <id LE16> <result> <size> <value>."""
    body = bytearray([0xB1, len(entries)])
    for prop, result, value in entries:
        body += prop.to_bytes(2, "little")
        body += bytes([result, len(value)])
        body += value
    body += bytes([0x00, api.crc8_854(list(body), 0, len(body) - 1)])
    return bytes(body)


def test_property_parsing_matches_capture():
    # Shape taken from a real B1 reply while cooling at 24.5C, 25.0C indoors.
    body = _reply_body(
        [
            (api.PROP_MODE, 0, b"\x02"),
            (api.PROP_TARGET_TEMP, 0, b"\x31"),
            (api.PROP_INDOOR_TEMP, 0, b"\x64\x00"),
            (api.PROP_OUTDOOR_TEMP, 0, b"\x4c\x06"),
            (api.PROP_FAN, 0, b"\x50"),
            (api.PROP_ECO, 0, b"\x01"),
        ]
    )
    values = api.parse_ac_properties_response(body)
    assert values[api.PROP_MODE] == "cool"
    assert values[api.PROP_TARGET_TEMP] == 24.5
    assert values[api.PROP_INDOOR_TEMP] == 25.0
    assert values[api.PROP_OUTDOOR_TEMP] == 13.6
    assert values[api.PROP_FAN] == "strong"
    assert values[api.PROP_ECO] is True


def test_fan_speed_names_round_trip():
    body = _reply_body([(api.PROP_FAN, 0, bytes([code])) for code in ()] or [
        (api.PROP_FAN, 0, b"\x3c"),
    ])
    assert api.parse_ac_properties_response(body)[api.PROP_FAN] == "mid"


def test_temperature_limit_is_16_to_30():
    # 0x3D (30.5C) is accepted by the API but silently ignored by the unit.
    assert api.AC_TEMPERATURE_MIN == 16.0
    assert api.AC_TEMPERATURE_MAX == 30.0
    assert int(api.AC_TEMPERATURE_MAX * 2) == 0x3C


def test_multi_property_payload_layout():
    payload = api.build_ac_set_properties_payload(
        [(api.PROP_MODE, [2]), (api.PROP_TARGET_TEMP, [48]), (api.PROP_FAN, [0x50])]
    )
    body = payload[16:-2]
    assert body[0] == api.AC_CONTROL_PROPERTY_CMD
    assert body[1] == 3
    # B0 <count> <id LE16> <size> <value> ...  (no result byte!)
    assert body[2:6] == bytes([0x02, 0x00, 0x01, 0x02])
    assert body[6:10] == bytes([0x03, 0x00, 0x01, 0x30])
    assert body[10:14] == bytes([0x06, 0x00, 0x01, 0x50])
    assert body[-1] == api.crc8_854(list(body), 0, len(body) - 2)


def test_uart_frame_crc():
    payload = api.build_ac_query_properties_payload([api.PROP_FAN])
    assert payload[0:4] == b"\x55\xAA\xCC\x33"
    stored = payload[-2] | (payload[-1] << 8)
    assert stored == api.crc16_ccitt(list(payload), 0, len(payload) - 3)


def test_datagram_layout():
    payload = api.build_ac_query_properties_payload([api.PROP_FAN])
    packet = api.build_wifidatagram(payload.hex(), "21990235976141")
    assert packet[0:2] == b"\x5A\x5A"
    assert int.from_bytes(packet[4:6], "little") == len(packet)
    parsed = api.parse_wifidatagram(packet)
    assert parsed["body"] == payload
