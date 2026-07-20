#!/usr/bin/env python3
import json
import os
import sys
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

API_BASE_URL = os.environ.get("OPEN_CHAT_RELAY_SMOKE_BASE_URL", "http://localhost:8000").rstrip("/")
GATEWAY_BASE_URL = os.environ.get(
    "OPEN_CHAT_RELAY_SMOKE_WEBTRANSPORT_GATEWAY_URL",
    "http://localhost:8081",
).rstrip("/")


def request_json(
    method: str,
    base_url: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{base_url}{path}"
    validate_http_url(url)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    request = Request(url, data=body, headers=headers, method=method)  # noqa: S310
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            response_body = response.read()
            if not response_body:
                return {}
            return json.loads(response_body.decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def request_text(
    method: str,
    base_url: str,
    path: str,
    *,
    payload: bytes,
    content_type: str,
) -> str:
    url = f"{base_url}{path}"
    validate_http_url(url)
    request = Request(  # noqa: S310
        url,
        data=payload,
        headers={"Accept": content_type, "Content-Type": content_type},
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            return response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {url} failed: {exc.reason}") from exc


def validate_http_url(url: str) -> None:
    scheme = urlparse(url).scheme
    if scheme not in {"http", "https"}:
        raise RuntimeError(f"Refusing non-HTTP URL: {url}")


def main() -> int:
    suffix = uuid.uuid4().hex[:12]
    email = f"gateway-smoke-{suffix}@example.com"
    password = "correct horse battery staple"  # noqa: S105

    print(f"API target: {API_BASE_URL}")
    print(f"Gateway target: {GATEWAY_BASE_URL}")

    gateway_health = request_json("GET", GATEWAY_BASE_URL, "/health")
    print(f"Gateway health: {gateway_health['status']}")

    gateway_ready = request_json("GET", GATEWAY_BASE_URL, "/ready")
    print(f"Gateway ready: {gateway_ready['status']}")

    auth = request_json(
        "POST",
        API_BASE_URL,
        "/v1/auth/register",
        payload={
            "email": email,
            "password": password,
            "display_name": "Gateway Smoke",
        },
    )
    token = auth["access_token"]
    workspace = request_json(
        "POST",
        API_BASE_URL,
        "/v1/workspaces",
        token=token,
        payload={"name": f"Gateway Smoke {suffix}"},
    )
    room = request_json(
        "POST",
        API_BASE_URL,
        f"/v1/workspaces/{workspace['id']}/rooms",
        token=token,
        payload={"name": "Gateway Room"},
    )

    command_response = request_json(
        "POST",
        GATEWAY_BASE_URL,
        "/internal/commands",
        payload={
            "access_token": token,
            "command": {
                "type": "message.send",
                "request_id": "gateway-smoke-message",
                "data": {
                    "room_id": room["id"],
                    "content": "hello through webtransport gateway relay",
                },
            },
        },
    )
    frames = command_response["frames"]
    if frames[0]["type"] != "ack":
        raise RuntimeError(f"Expected ack frame, got: {frames[0]}")
    if frames[1]["type"] != "message.created":
        raise RuntimeError(f"Expected message.created frame, got: {frames[1]}")
    print(f"Gateway command relay event: {frames[1]['event_id']}")

    replay_response = request_json(
        "POST",
        GATEWAY_BASE_URL,
        "/internal/commands",
        payload={
            "access_token": token,
            "command": {
                "type": "room.subscribe",
                "request_id": "gateway-smoke-subscribe",
                "data": {"room_id": room["id"], "last_event_seq": 0},
            },
        },
    )
    replay_frames = replay_response["frames"]
    if len(replay_frames) < 2 or replay_frames[1]["type"] != "message.created":
        raise RuntimeError(f"Expected replayed message event, got: {replay_frames}")
    print("Gateway replay returned message event.")

    presence_response = request_json(
        "POST",
        GATEWAY_BASE_URL,
        "/internal/commands",
        payload={
            "access_token": token,
            "command": {
                "type": "presence.update",
                "request_id": "gateway-smoke-presence",
                "data": {"room_id": room["id"], "status": "online"},
            },
        },
    )
    presence_frames = presence_response["frames"]
    if len(presence_frames) != 2 or presence_frames[1]["type"] != "presence.updated":
        raise RuntimeError(f"Expected presence.updated frame, got: {presence_frames}")
    print("Gateway presence relay returned signal event.")

    typing_response = request_json(
        "POST",
        GATEWAY_BASE_URL,
        "/internal/commands",
        payload={
            "access_token": token,
            "command": {
                "type": "typing.update",
                "request_id": "gateway-smoke-typing",
                "data": {"room_id": room["id"], "status": "started"},
            },
        },
    )
    typing_frames = typing_response["frames"]
    if len(typing_frames) != 2 or typing_frames[1]["type"] != "typing.updated":
        raise RuntimeError(f"Expected typing.updated frame, got: {typing_frames}")
    print("Gateway typing relay returned signal event.")

    gateway_session = request_json(
        "POST",
        GATEWAY_BASE_URL,
        "/internal/sessions",
        payload={"access_token": token},
    )
    stream_text = request_text(
        "POST",
        GATEWAY_BASE_URL,
        f"/internal/sessions/{gateway_session['session_id']}/streams",
        payload=(
            json.dumps(
                {
                    "type": "room.subscribe",
                    "request_id": "gateway-smoke-stream-subscribe",
                    "data": {"room_id": room["id"], "last_event_seq": 0},
                }
            )
            + "\n"
        ).encode("utf-8"),
        content_type="application/x-ndjson",
    )
    stream_frames = [json.loads(line) for line in stream_text.splitlines() if line.strip()]
    if len(stream_frames) < 2 or stream_frames[1]["type"] != "message.created":
        raise RuntimeError(f"Expected streamed replay event, got: {stream_frames}")
    print("Gateway stream relay returned message event.")

    print("WebTransport gateway smoke passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Gateway smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
