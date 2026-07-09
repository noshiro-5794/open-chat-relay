from httpx import AsyncClient


async def test_gateway_can_authenticate_access_token(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "gateway-user@example.com",
            "password": "correct horse battery staple",
            "display_name": "Gateway User",
        },
    )
    auth_body = register_response.json()

    response = await client.post(
        "/v1/internal/gateway/authenticate",
        headers={"X-OpenChatRelay-Gateway-Token": "test-gateway-token"},
        json={"access_token": auth_body["access_token"]},
    )

    assert response.status_code == 200
    assert response.json()["user_id"] == auth_body["user"]["id"]
    assert response.json()["token_expires_at"]


async def test_gateway_authentication_requires_internal_token(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "gateway-missing-token@example.com",
            "password": "correct horse battery staple",
            "display_name": "Gateway User",
        },
    )

    response = await client.post(
        "/v1/internal/gateway/authenticate",
        json={"access_token": register_response.json()["access_token"]},
    )

    assert response.status_code == 401


async def test_gateway_authentication_rejects_wrong_internal_token(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "gateway-wrong-token@example.com",
            "password": "correct horse battery staple",
            "display_name": "Gateway User",
        },
    )

    response = await client.post(
        "/v1/internal/gateway/authenticate",
        headers={"X-OpenChatRelay-Gateway-Token": "wrong-token"},
        json={"access_token": register_response.json()["access_token"]},
    )

    assert response.status_code == 401


async def test_gateway_authentication_rejects_refresh_token(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "gateway-refresh-token@example.com",
            "password": "correct horse battery staple",
            "display_name": "Gateway User",
        },
    )

    response = await client.post(
        "/v1/internal/gateway/authenticate",
        headers={"X-OpenChatRelay-Gateway-Token": "test-gateway-token"},
        json={"access_token": register_response.json()["refresh_token"]},
    )

    assert response.status_code == 401


async def test_gateway_command_can_send_message(client: AsyncClient) -> None:
    auth_body, room = await create_gateway_room(client, email="gateway-command@example.com")

    response = await client.post(
        "/v1/internal/gateway/commands",
        headers={"X-OpenChatRelay-Gateway-Token": "test-gateway-token"},
        json={
            "access_token": auth_body["access_token"],
            "command": {
                "type": "message.send",
                "request_id": "msg-1",
                "data": {"room_id": room["id"], "content": "hello from gateway"},
            },
        },
    )

    assert response.status_code == 200
    frames = response.json()["frames"]
    assert frames[0]["type"] == "ack"
    assert frames[0]["request_id"] == "msg-1"
    assert frames[0]["event_id"]
    assert frames[1]["type"] == "message.created"
    assert frames[1]["data"]["content"] == "hello from gateway"


async def test_gateway_command_subscribe_replays_missed_events(client: AsyncClient) -> None:
    auth_body, room = await create_gateway_room(client, email="gateway-replay@example.com")
    headers = {"Authorization": f"Bearer {auth_body['access_token']}"}
    await client.post(
        f"/v1/rooms/{room['id']}/messages",
        headers=headers,
        json={"content": "one"},
    )
    await client.post(
        f"/v1/rooms/{room['id']}/messages",
        headers=headers,
        json={"content": "two"},
    )

    response = await client.post(
        "/v1/internal/gateway/commands",
        headers={"X-OpenChatRelay-Gateway-Token": "test-gateway-token"},
        json={
            "access_token": auth_body["access_token"],
            "command": {
                "type": "room.subscribe",
                "request_id": "sub-1",
                "data": {"room_id": room["id"], "last_event_seq": 1},
            },
        },
    )

    assert response.status_code == 200
    frames = response.json()["frames"]
    assert frames[0] == {"type": "ack", "request_id": "sub-1", "status": "ok", "event_id": None}
    assert frames[1]["type"] == "message.created"
    assert frames[1]["room_event_seq"] == 2
    assert frames[1]["data"]["content"] == "two"


async def test_gateway_command_can_update_presence(client: AsyncClient) -> None:
    auth_body, room = await create_gateway_room(client, email="gateway-presence@example.com")

    response = await client.post(
        "/v1/internal/gateway/commands",
        headers={"X-OpenChatRelay-Gateway-Token": "test-gateway-token"},
        json={
            "access_token": auth_body["access_token"],
            "command": {
                "type": "presence.update",
                "request_id": "presence-1",
                "data": {"room_id": room["id"], "status": "away"},
            },
        },
    )

    assert response.status_code == 200
    frames = response.json()["frames"]
    assert frames[0] == {
        "type": "ack",
        "request_id": "presence-1",
        "status": "ok",
        "event_id": None,
    }
    assert frames[1]["type"] == "presence.updated"
    assert frames[1]["room_id"] == room["id"]
    assert frames[1]["data"]["status"] == "away"


async def test_gateway_command_can_update_typing(client: AsyncClient) -> None:
    auth_body, room = await create_gateway_room(client, email="gateway-typing@example.com")

    response = await client.post(
        "/v1/internal/gateway/commands",
        headers={"X-OpenChatRelay-Gateway-Token": "test-gateway-token"},
        json={
            "access_token": auth_body["access_token"],
            "command": {
                "type": "typing.update",
                "request_id": "typing-1",
                "data": {"room_id": room["id"], "status": "started"},
            },
        },
    )

    assert response.status_code == 200
    frames = response.json()["frames"]
    assert frames[0] == {
        "type": "ack",
        "request_id": "typing-1",
        "status": "ok",
        "event_id": None,
    }
    assert frames[1]["type"] == "typing.updated"
    assert frames[1]["room_id"] == room["id"]
    assert frames[1]["data"]["status"] == "started"


async def test_gateway_command_invalid_typing_update_returns_error_frame(
    client: AsyncClient,
) -> None:
    auth_body, room = await create_gateway_room(client, email="gateway-invalid-typing@example.com")

    response = await client.post(
        "/v1/internal/gateway/commands",
        headers={"X-OpenChatRelay-Gateway-Token": "test-gateway-token"},
        json={
            "access_token": auth_body["access_token"],
            "command": {
                "type": "typing.update",
                "request_id": "typing-bad-1",
                "data": {"room_id": room["id"], "status": "invalid"},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["frames"] == [
        {
            "type": "error",
            "request_id": "typing-bad-1",
            "code": "invalid_typing",
            "message": "typing.update requires room_id and status.",
        }
    ]


async def test_gateway_command_unknown_command_returns_error_frame(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "gateway-unknown@example.com",
            "password": "correct horse battery staple",
            "display_name": "Gateway User",
        },
    )

    response = await client.post(
        "/v1/internal/gateway/commands",
        headers={"X-OpenChatRelay-Gateway-Token": "test-gateway-token"},
        json={
            "access_token": register_response.json()["access_token"],
            "command": {"type": "unknown.command", "request_id": "bad-1", "data": {}},
        },
    )

    assert response.status_code == 200
    assert response.json()["frames"] == [
        {
            "type": "error",
            "request_id": "bad-1",
            "code": "unknown_command",
            "message": "Unknown gateway command.",
        }
    ]


async def create_gateway_room(client: AsyncClient, *, email: str) -> tuple[dict, dict]:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "Gateway User",
        },
    )
    auth_body = register_response.json()
    headers = {"Authorization": f"Bearer {auth_body['access_token']}"}
    workspace_response = await client.post(
        "/v1/workspaces",
        headers=headers,
        json={"name": "Gateway Team"},
    )
    room_response = await client.post(
        f"/v1/workspaces/{workspace_response.json()['id']}/rooms",
        headers=headers,
        json={"name": "Gateway Room"},
    )
    return auth_body, room_response.json()
