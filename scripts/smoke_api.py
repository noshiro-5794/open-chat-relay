#!/usr/bin/env python3
import json
import os
import sys
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

BASE_URL = os.environ.get("OPEN_CHAT_RELAY_SMOKE_BASE_URL", "http://localhost:8000").rstrip("/")


def request_json(
    method: str,
    path_or_url: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    url = path_or_url if path_or_url.startswith("http") else f"{BASE_URL}{path_or_url}"
    validate_http_url(url)
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"Accept": "application/json"}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    if token is not None:
        request_headers["Authorization"] = f"Bearer {token}"
    if headers:
        request_headers.update(headers)

    request = Request(url, data=body, headers=request_headers, method=method)  # noqa: S310
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


def put_bytes(url: str, *, content: bytes, content_type: str) -> None:
    validate_http_url(url)
    request = Request(  # noqa: S310
        url,
        data=content,
        headers={"Content-Type": content_type},
        method="PUT",
    )
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310
            if response.status not in {200, 201, 204}:
                raise RuntimeError(f"PUT {url} returned {response.status}")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"PUT presigned upload failed with {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"PUT presigned upload failed: {exc.reason}") from exc


def validate_http_url(url: str) -> None:
    scheme = urlparse(url).scheme
    if scheme not in {"http", "https"}:
        raise RuntimeError(f"Refusing non-HTTP URL: {url}")


def main() -> int:
    suffix = uuid.uuid4().hex[:12]
    email = f"smoke-{suffix}@example.com"
    password = "correct horse battery staple"  # noqa: S105
    attachment_bytes = b"OpenChatRelay smoke upload\n"

    print(f"Smoke target: {BASE_URL}")
    health = request_json("GET", "/health")
    print(f"Health: {health['status']}")

    auth = request_json(
        "POST",
        "/v1/auth/register",
        payload={
            "email": email,
            "password": password,
            "display_name": "Smoke User",
        },
    )
    token = auth["access_token"]
    print(f"Registered: {email}")

    workspace = request_json(
        "POST",
        "/v1/workspaces",
        token=token,
        payload={"name": f"Smoke Workspace {suffix}"},
    )
    room = request_json(
        "POST",
        f"/v1/workspaces/{workspace['id']}/rooms",
        token=token,
        payload={"name": "Smoke Room"},
    )
    print(f"Created room: {room['id']}")

    intent = request_json(
        "POST",
        f"/v1/rooms/{room['id']}/attachments",
        token=token,
        payload={
            "filename": "smoke.txt",
            "content_type": "text/plain",
            "size_bytes": len(attachment_bytes),
        },
    )
    upload_url = intent["upload_url"]
    if not upload_url:
        raise RuntimeError("Attachment upload URL was not returned.")

    put_bytes(upload_url, content=attachment_bytes, content_type="text/plain")
    attachment = request_json(
        "POST",
        f"/v1/rooms/{room['id']}/attachments/{intent['attachment']['id']}/confirm",
        token=token,
    )
    print(f"Confirmed attachment: {attachment['id']}")

    message = request_json(
        "POST",
        f"/v1/rooms/{room['id']}/messages",
        token=token,
        payload={
            "content": "smoke message",
            "attachment_ids": [attachment["id"]],
        },
    )
    print(f"Created message: {message['id']}")

    message_page = request_json(
        "GET",
        f"/v1/rooms/{room['id']}/messages/page?limit=1",
        token=token,
    )
    if not message_page["items"] or message_page["items"][0]["id"] != message["id"]:
        raise RuntimeError("Message page did not include the created message.")
    print("Read message history page.")

    download = request_json(
        "GET",
        f"/v1/rooms/{room['id']}/attachments/{attachment['id']}/download",
        token=token,
    )
    if not download["download_url"]:
        raise RuntimeError("Attachment download URL was not returned.")
    print(f"Created attachment download intent: {attachment['id']}")

    print("Smoke passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
