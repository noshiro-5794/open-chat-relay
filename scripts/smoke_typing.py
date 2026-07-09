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
    email = f"typing-smoke-{suffix}@example.com"
    password = "correct horse battery staple"  # noqa: S105

    print(f"Typing smoke target: {BASE_URL}")
    auth = smoke_api.request_json(
        "POST",
        "/v1/auth/register",
        payload={
            "email": email,
            "password": password,
            "display_name": "Typing Smoke User",
        },
    )
    token = auth["access_token"]
    workspace = smoke_api.request_json(
        "POST",
        "/v1/workspaces",
        token=token,
        payload={"name": f"Typing Smoke Workspace {suffix}"},
    )
    room = smoke_api.request_json(
        "POST",
        f"/v1/workspaces/{workspace['id']}/rooms",
        token=token,
        payload={"name": "Typing Smoke Room"},
    )

    async with websockets.connect(f"{WS_URL}?token={quote(token)}", proxy=None) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "room.subscribe",
                    "request_id": "typing-smoke-subscribe",
                    "data": {"room_id": room["id"]},
                }
            )
        )
        subscribe_ack = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if subscribe_ack.get("type") != "ack":
            raise RuntimeError(f"Unexpected subscribe response: {subscribe_ack}")

        await websocket.send(
            json.dumps(
                {
                    "type": "typing.update",
                    "request_id": "typing-smoke-started",
                    "data": {"room_id": room["id"], "status": "started"},
                }
            )
        )
        start_ack = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if start_ack.get("type") != "ack":
            raise RuntimeError(f"Unexpected typing start response: {start_ack}")

        typing = smoke_api.request_json(
            "GET",
            f"/v1/rooms/{room['id']}/typing",
            token=token,
        )
        assert_one_typing_user(typing)
        print("Typing started state observed.")

        await websocket.send(
            json.dumps(
                {
                    "type": "typing.update",
                    "request_id": "typing-smoke-stopped",
                    "data": {"room_id": room["id"], "status": "stopped"},
                }
            )
        )
        stop_ack = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if stop_ack.get("type") != "ack":
            raise RuntimeError(f"Unexpected typing stop response: {stop_ack}")

        typing = smoke_api.request_json(
            "GET",
            f"/v1/rooms/{room['id']}/typing",
            token=token,
        )
        if typing["users"]:
            raise RuntimeError(f"Expected empty typing state after stopped: {typing}")

    print("Typing stopped state observed.")
    print("Typing smoke passed.")
    return 0


def assert_one_typing_user(typing: dict) -> None:
    users = typing.get("users")
    if not isinstance(users, list) or len(users) != 1:
        raise RuntimeError(f"Expected exactly one typing user: {typing}")
    if users[0].get("status") != "started":
        raise RuntimeError(f"Expected typing status 'started': {typing}")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"Typing smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
