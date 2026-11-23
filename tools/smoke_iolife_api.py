"""Live smoke test for custom_components.iolife.api against the real unit.

Two ways to authenticate:

  * ``--use-saved-session`` reuses the ``session.json`` written by ``main.py``
    (no password needed, handy for local verification).
  * otherwise ``IOLIFE_EMAIL`` / ``IOLIFE_PASSWORD`` are used and the full
    login flow runs.

Read-only unless ``--write`` is given; ``--write`` exercises the fan speed
controls and prints what the unit reports afterwards.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import aiohttp

from custom_components.iolife import api

SESSION_FILE = pathlib.Path(__file__).resolve().parent.parent / "session.json"


def session_from_file() -> api.IolifeSession:
    data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    data_key = data.get("dataKey") or api.decode_with_app_key(data["accessToken"])
    return api.IolifeSession(
        login_id=str(data.get("loginId")),
        session_id=str(data["sessionId"]),
        user_id=str(data.get("userId")),
        data_key=data_key,
        data_iv=data.get("dataIV"),
    )


async def run(appliance_id: str, do_writes: bool, use_saved: bool) -> int:
    async with aiohttp.ClientSession() as http:
        if use_saved:
            client = api.IolifeClient(http, "", "")
            client.session = session_from_file()
            print(f"using saved session {client.session.session_id[:8]}...")
            devices = await client.async_list_devices()
        else:
            client = api.IolifeClient(
                http, os.environ["IOLIFE_EMAIL"], os.environ["IOLIFE_PASSWORD"]
            )
            session = await client.async_login()
            print(f"logged in userId={session.user_id} sessionId={session.session_id[:8]}...")
            devices = await client.async_list_devices()

        for device in devices:
            print(
                f"device: {device.get('id')} {device.get('name')} "
                f"type={device.get('type')} online={device.get('onlineStatus')}"
            )

        state = await client.async_query_properties(appliance_id)
        print("state:", json.dumps({f"0x{k:02X}": v for k, v in state.items()}, ensure_ascii=False))

        if not do_writes:
            return 0

        original = state.get(api.PROP_FAN)
        for speed in ("mid", "weak", "strong"):
            await client.async_set_properties(
                appliance_id, [(api.PROP_FAN, [api.AC_FAN_SPEEDS[speed]])]
            )
            await asyncio.sleep(2.0)
            current = (await client.async_query_properties(appliance_id, [api.PROP_FAN]))[
                api.PROP_FAN
            ]
            print(f"fan -> requested {speed}, unit reports {current}")
        print(f"fan original was {original}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--appliance-id", required=True)
    parser.add_argument("--write", action="store_true", help="also exercise fan speed writes")
    parser.add_argument("--use-saved-session", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.appliance_id, args.write, args.use_saved_session))


if __name__ == "__main__":
    raise SystemExit(main())
