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
    netloc = parsed.netloc
    return f"{scheme}://{netloc}/v1/ws"


BASE_URL = smoke_api.BASE_URL
WS_URL = os.environ.get("OPEN_CHAT_RELAY_SMOKE_WS_URL", websocket_url_from_base(BASE_URL))


async def main() -> int:
    suffix = uuid.uuid4().hex[:12]
    email = f"realtime-smoke-{suffix}@example.com"
    password = "correct horse battery staple"  # noqa: S105
    content = f"realtime smoke {suffix}"

    print(f"Realtime smoke target: {BASE_URL}")
    print(f"Realtime websocket target: {WS_URL}")
    health = smoke_api.request_json("GET", "/health")
    print(f"Health: {health['status']}")

    auth = smoke_api.request_json(
        "POST",
        "/v1/auth/register",
        payload={
            "email": email,
            "password": password,
            "display_name": "Realtime Smoke User",
        },
    )
    token = auth["access_token"]

    workspace = smoke_api.request_json(
        "POST",
        "/v1/workspaces",
        token=token,
        payload={"name": f"Realtime Smoke Workspace {suffix}"},
    )
    room = smoke_api.request_json(
        "POST",
        f"/v1/workspaces/{workspace['id']}/rooms",
        token=token,
        payload={"name": "Realtime Smoke Room"},
    )

    async with websockets.connect(f"{WS_URL}?token={quote(token)}", proxy=None) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "type": "room.subscribe",
                    "request_id": "realtime-smoke-subscribe",
                    "data": {"room_id": room["id"]},
                }
            )
        )
        subscribe_ack = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if subscribe_ack.get("type") != "ack":
            raise RuntimeError(f"Unexpected subscribe response: {subscribe_ack}")

        message = await asyncio.to_thread(
            smoke_api.request_json,
            "POST",
            f"/v1/rooms/{room['id']}/messages",
            token=token,
            payload={"content": content},
        )
        print(f"Created REST message: {message['id']}")

        event = json.loads(await asyncio.wait_for(websocket.recv(), timeout=10))
        if event.get("type") != "message.created":
            raise RuntimeError(f"Unexpected realtime event: {event}")
        if event.get("room_id") != room["id"] or event.get("data", {}).get("content") != content:
            raise RuntimeError(f"Realtime event did not match created message: {event}")

        print(f"Received realtime event: {event['event_id']}")

    print("Realtime smoke passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f"Realtime smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
