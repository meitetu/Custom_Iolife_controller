#!/usr/bin/env python3
"""Probe AC state/property decoding against a real unit.

Run this after changing the 0xC0 layout or property decoding. It only sends
queries; it does not change any setting.

    python3 tools/probe_ac.py --appliance-id 21990235976141
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import main


def main_() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--appliance-id", required=True)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    session = main.load_session()
    session_id = session["sessionId"]
    client = main.IoLifeClient(language="ja_JP")

    def send(payload: bytes) -> bytes:
        order = main.build_order_from_payload(
            session, payload.hex().upper(), args.appliance_id
        )
        resp = client.transparent_send(session_id, args.appliance_id, order)
        body = main.decode_transparent_reply(session, resp)
        if body is None:
            raise SystemExit("reply could not be decoded")
        return body

    import time

    for index in range(args.repeat):
        if index:
            time.sleep(args.interval)
        state = main.decode_ac_state_body(send(main.build_ac_query_payload("all")))
        props = main.parse_ac_properties_response(
            send(main.build_ac_query_properties_payload(main.AC_ALL_PROPERTIES))
        )
        print(json.dumps({"state": state, "properties": props}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_())
