#!/usr/bin/env python3
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

API_BASE_URL = os.environ.get("OPEN_CHAT_RELAY_DEPLOY_API_URL", "http://localhost:8000").rstrip("/")
CONSOLE_BASE_URL = os.environ.get(
    "OPEN_CHAT_RELAY_DEPLOY_CONSOLE_URL",
    "http://localhost:5173",
).rstrip("/")
GATEWAY_BASE_URL = os.environ.get("OPEN_CHAT_RELAY_DEPLOY_GATEWAY_URL", "").rstrip("/")

EXPECTED_FRAME_VERSION = "ocr.realtime.frame.v1"
EXPECTED_FRAME_ENCODING = "jsonl"
EXPECTED_FRAME_CONTENT_TYPE = "application/x-ndjson"


def request_json(base_url: str, path: str) -> dict[str, Any]:
    url = f"{base_url}{path}"
    validate_http_url(url)
    request = Request(url, headers={"Accept": "application/json"}, method="GET")  # noqa: S310
    try:
        with urlopen(request, timeout=10) as response:  # noqa: S310
            body = response.read()
            if not body:
                return {}
            return json.loads(body.decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed with {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"GET {url} failed: {exc.reason}") from exc


def validate_http_url(url: str) -> None:
    scheme = urlparse(url).scheme
    if scheme not in {"http", "https"}:
        raise RuntimeError(f"Refusing non-HTTP URL: {url}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def check_api() -> dict[str, Any]:
    print(f"API: {API_BASE_URL}")
    health = request_json(API_BASE_URL, "/health")
    require(health.get("status") == "ok", f"Unexpected API health: {health}")
    print("  health ok")

    ready = request_json(API_BASE_URL, "/ready")
    require(ready.get("status") == "ready", f"Unexpected API readiness: {ready}")
    print("  ready ok")

    capabilities = request_json(API_BASE_URL, "/v1/capabilities")
    require(
        capabilities["transports"]["websocket"]["available"] is True,
        "WebSocket transport must be available.",
    )
    frame = capabilities["realtime_frame"]
    validate_frame_protocol(frame)
    print(f"  frame protocol {frame['version']} / {frame['encoding']}")

    webtransport = capabilities["transports"]["webtransport"]
    print(f"  webtransport {webtransport['status']}")
    return capabilities


def check_console() -> None:
    if not CONSOLE_BASE_URL:
        print("Console: skipped")
        return
    print(f"Console: {CONSOLE_BASE_URL}")
    health = request_json(CONSOLE_BASE_URL, "/health")
    require(health.get("status") == "ok", f"Unexpected console health: {health}")
    print("  health ok")


def check_gateway() -> None:
    if not GATEWAY_BASE_URL:
        print("WebTransport gateway: skipped")
        return
    print(f"WebTransport gateway: {GATEWAY_BASE_URL}")
    ready = request_json(GATEWAY_BASE_URL, "/ready")
    require(ready.get("status") == "ready", f"Unexpected gateway readiness: {ready}")
    validate_frame_protocol(ready["frame_protocol"])
    print("  ready ok")


def validate_frame_protocol(frame: dict[str, Any]) -> None:
    require(frame.get("version") == EXPECTED_FRAME_VERSION, "Unexpected frame protocol version.")
    require(frame.get("encoding") == EXPECTED_FRAME_ENCODING, "Unexpected frame encoding.")
    require(
        frame.get("content_type") == EXPECTED_FRAME_CONTENT_TYPE,
        "Unexpected frame content type.",
    )
    require(
        isinstance(frame.get("max_frame_bytes"), int) and frame["max_frame_bytes"] > 0,
        "Frame max size must be a positive integer.",
    )


def main() -> int:
    check_api()
    check_console()
    check_gateway()
    print("Deployment check passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Deployment check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
