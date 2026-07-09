#!/usr/bin/env python3
import asyncio
import json
import os
import sys
import uuid
from urllib.parse import quote, urlparse

import smoke_api
import websockets


def websocket_url_from_base(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/v1/ws"


BASE_URL = smoke_api.BASE_URL
WS_URL = os.environ.get("OPEN_CHAT_RELAY_SMOKE_WS_URL", websocket_url_from_base(BASE_URL))


async def main() -> int:
    suffix = uuid.uuid4().hex[:12]
    email = f"presence-smoke-{suffix}@example.com"
    password = "correct horse battery staple"  # noqa: S105

    print(f"Presence smoke target: {BASE_URL}")
    auth = smoke_api.request_json(
        "POST",
        "/v1/auth/register",
        payload={
            "email": email,
            "password": password,
            "display_name": "Presence Smoke User",
        },
    )
    token = auth["access_token"]
    workspace = smoke_api.request_json(
        "POST",
        "/v1/workspaces",
        token=token,
        payload={"name": f"Presence Smoke Workspace {suffix}"},
    )
    room = smoke_api.request_json(
        "POST",
        f"/v1/workspaces/{workspace['id']}/rooms",
        token=token,
        payload={"name": "Presence Smoke Room"},
    )

    async with websockets.connect(f"{WS_URL}?token={quote(token)}", proxy=None) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "room.subscribe",
                    "request_id": "presence-smoke-subscribe",
                    "data": {"room_id": room["id"]},
                }
            )
        )
        subscribe_ack = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if subscribe_ack.get("type") != "ack":
            raise RuntimeError(f"Unexpected subscribe response: {subscribe_ack}")

        presence = smoke_api.request_json(
            "GET",
            f"/v1/rooms/{room['id']}/presence",
            token=token,
        )
        assert_one_presence_user(presence, expected_status="online")
        print("Presence online state observed.")

        await websocket.send(
            json.dumps(
                {
                    "type": "presence.update",
                    "request_id": "presence-smoke-away",
                    "data": {"room_id": room["id"], "status": "away"},
                }
            )
        )
        update_ack = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if update_ack.get("type") != "ack":
            raise RuntimeError(f"Unexpected presence update response: {update_ack}")

        presence = smoke_api.request_json(
            "GET",
            f"/v1/rooms/{room['id']}/presence",
            token=token,
        )
        assert_one_presence_user(presence, expected_status="away")
        print("Presence away state observed.")

    await asyncio.sleep(0.2)
    presence = smoke_api.request_json(
        "GET",
        f"/v1/rooms/{room['id']}/presence",
        token=token,
    )
    if presence["users"]:
        raise RuntimeError(f"Expected empty presence after disconnect: {presence}")

    print("Presence offline state observed.")
    print("Presence smoke passed.")
    return 0


def assert_one_presence_user(presence: dict, *, expected_status: str) -> None:
    users = presence.get("users")
    if not isinstance(users, list) or len(users) != 1:
        raise RuntimeError(f"Expected exactly one presence user: {presence}")
    status = users[0].get("status")
    if status != expected_status:
        raise RuntimeError(f"Expected presence status {expected_status!r}: {presence}")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"Presence smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
