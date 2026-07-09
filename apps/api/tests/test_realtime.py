from starlette.testclient import TestClient


def auth_headers(client: TestClient, email: str = "owner@example.com") -> dict[str, str]:
    response = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "Owner",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_room(client: TestClient, headers: dict[str, str]) -> dict:
    workspace_response = client.post(
        "/v1/workspaces",
        json={"name": "Realtime Team"},
        headers=headers,
    )
    workspace_id = workspace_response.json()["id"]
    room_response = client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "General"},
        headers=headers,
    )
    return room_response.json()


def test_websocket_subscribe_send_and_receive_event(sync_client: TestClient) -> None:
    headers = auth_headers(sync_client)
    room = create_room(sync_client, headers)
    token = headers["Authorization"].removeprefix("Bearer ")

    with sync_client.websocket_connect(f"/v1/ws?token={token}") as websocket:
        websocket.send_json(
            {
                "type": "room.subscribe",
                "request_id": "sub-1",
                "data": {"room_id": room["id"]},
            }
        )
        subscribe_ack = websocket.receive_json()
        assert subscribe_ack["type"] == "ack"
        assert subscribe_ack["request_id"] == "sub-1"

        websocket.send_json(
            {
                "type": "message.send",
                "request_id": "msg-1",
                "data": {"room_id": room["id"], "content": "hello realtime"},
            }
        )

        message_ack = websocket.receive_json()
        event = websocket.receive_json()

        assert message_ack["type"] == "ack"
        assert message_ack["request_id"] == "msg-1"
        assert message_ack["event_id"]
        assert event["type"] == "message.created"
        assert event["room_event_seq"] == 1
        assert event["data"]["content"] == "hello realtime"


def test_websocket_unknown_command_returns_error(sync_client: TestClient) -> None:
    headers = auth_headers(sync_client)
    token = headers["Authorization"].removeprefix("Bearer ")

    with sync_client.websocket_connect(f"/v1/ws?token={token}") as websocket:
        websocket.send_json({"type": "unknown.command", "request_id": "bad-1", "data": {}})
        error = websocket.receive_json()

        assert error["type"] == "error"
        assert error["request_id"] == "bad-1"
        assert error["code"] == "unknown_command"


def test_websocket_message_send_supports_reply(sync_client: TestClient) -> None:
    headers = auth_headers(sync_client)
    room = create_room(sync_client, headers)
    token = headers["Authorization"].removeprefix("Bearer ")
    parent_response = sync_client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "parent"},
        headers=headers,
    )
    parent = parent_response.json()

    with sync_client.websocket_connect(f"/v1/ws?token={token}") as websocket:
        websocket.send_json(
            {
                "type": "room.subscribe",
                "request_id": "sub-1",
                "data": {"room_id": room["id"]},
            }
        )
        assert websocket.receive_json()["type"] == "ack"

        websocket.send_json(
            {
                "type": "message.send",
                "request_id": "reply-1",
                "data": {
                    "room_id": room["id"],
                    "content": "reply over ws",
                    "reply_to_id": parent["id"],
                },
            }
        )

        assert websocket.receive_json()["type"] == "ack"
        event = websocket.receive_json()
        assert event["type"] == "message.created"
        assert event["data"]["content"] == "reply over ws"
        assert event["data"]["reply_to_id"] == parent["id"]


def test_websocket_receives_user_notification(sync_client: TestClient) -> None:
    owner_headers = auth_headers(sync_client, email="notify-owner@example.com")
    member_headers = auth_headers(sync_client, email="notify-member@example.com")
    room = create_room(sync_client, owner_headers)
    member = sync_client.get("/v1/me", headers=member_headers).json()
    sync_client.post(
        f"/v1/workspaces/{room['workspace_id']}/members",
        json={"email": "notify-member@example.com"},
        headers=owner_headers,
    )
    sync_client.post(
        f"/v1/rooms/{room['id']}/members",
        json={"user_id": member["id"]},
        headers=owner_headers,
    )
    member_token = member_headers["Authorization"].removeprefix("Bearer ")

    with sync_client.websocket_connect(f"/v1/ws?token={member_token}") as websocket:
        response = sync_client.post(
            f"/v1/rooms/{room['id']}/messages",
            json={"content": "notify over websocket"},
            headers=owner_headers,
        )
        notification = websocket.receive_json()

    assert response.status_code == 201
    assert notification["type"] == "notification.created"
    assert notification["user_id"] == member["id"]
    assert notification["data"]["body"] == "notify over websocket"


def test_websocket_invalid_message_command_returns_error(sync_client: TestClient) -> None:
    headers = auth_headers(sync_client)
    token = headers["Authorization"].removeprefix("Bearer ")

    with sync_client.websocket_connect(f"/v1/ws?token={token}") as websocket:
        websocket.send_json(
            {
                "type": "message.send",
                "request_id": "bad-message",
                "data": {"content": ""},
            }
        )
        error = websocket.receive_json()

        assert error["type"] == "error"
        assert error["request_id"] == "bad-message"
        assert error["code"] == "invalid_message"


def test_websocket_subscribe_replays_missed_events(sync_client: TestClient) -> None:
    headers = auth_headers(sync_client)
    room = create_room(sync_client, headers)
    token = headers["Authorization"].removeprefix("Bearer ")

    first_response = sync_client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "one"},
        headers=headers,
    )
    second_response = sync_client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "two"},
        headers=headers,
    )
    assert first_response.status_code == 201
    assert second_response.status_code == 201

    with sync_client.websocket_connect(f"/v1/ws?token={token}") as websocket:
        websocket.send_json(
            {
                "type": "room.subscribe",
                "request_id": "resume-1",
                "data": {"room_id": room["id"], "last_event_seq": 1},
            }
        )

        ack = websocket.receive_json()
        replayed_event = websocket.receive_json()

        assert ack["type"] == "ack"
        assert ack["request_id"] == "resume-1"
        assert replayed_event["type"] == "message.created"
        assert replayed_event["room_event_seq"] == 2
        assert replayed_event["data"]["content"] == "two"


def test_websocket_typing_update_broadcasts_ephemeral_signal(
    sync_client: TestClient,
) -> None:
    headers = auth_headers(sync_client)
    room = create_room(sync_client, headers)
    token = headers["Authorization"].removeprefix("Bearer ")

    with (
        sync_client.websocket_connect(f"/v1/ws?token={token}") as listener,
        sync_client.websocket_connect(f"/v1/ws?token={token}") as sender,
    ):
        listener.send_json(
            {
                "type": "room.subscribe",
                "request_id": "listener-sub",
                "data": {"room_id": room["id"]},
            }
        )
        assert listener.receive_json()["type"] == "ack"

        sender.send_json(
            {
                "type": "room.subscribe",
                "request_id": "sender-sub",
                "data": {"room_id": room["id"]},
            }
        )
        assert sender.receive_json()["type"] == "ack"

        sender.send_json(
            {
                "type": "typing.update",
                "request_id": "typing-1",
                "data": {"room_id": room["id"], "status": "started"},
            }
        )

        assert sender.receive_json()["type"] == "ack"
        event = listener.receive_json()
        assert event["type"] == "typing.updated"
        assert event["delivery"]["lane"] == "signal"
        assert event["data"]["room_id"] == room["id"]
        assert event["data"]["status"] == "started"

        typing_response = sync_client.get(f"/v1/rooms/{room['id']}/typing", headers=headers)
        assert typing_response.status_code == 200
        assert typing_response.json()["users"] == [
            {"user_id": event["data"]["user_id"], "status": "started"}
        ]

        sender.send_json(
            {
                "type": "typing.update",
                "request_id": "typing-2",
                "data": {"room_id": room["id"], "status": "stopped"},
            }
        )
        assert sender.receive_json()["type"] == "ack"
        assert listener.receive_json()["data"]["status"] == "stopped"
        typing_response = sync_client.get(f"/v1/rooms/{room['id']}/typing", headers=headers)
        assert typing_response.status_code == 200
        assert typing_response.json()["users"] == []

    events_response = sync_client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    assert events_response.status_code == 200
    assert events_response.json() == []


def test_websocket_invalid_typing_update_returns_error(sync_client: TestClient) -> None:
    headers = auth_headers(sync_client)
    room = create_room(sync_client, headers)
    token = headers["Authorization"].removeprefix("Bearer ")

    with sync_client.websocket_connect(f"/v1/ws?token={token}") as websocket:
        websocket.send_json(
            {
                "type": "typing.update",
                "request_id": "bad-typing",
                "data": {"room_id": room["id"], "status": "invalid"},
            }
        )
        error = websocket.receive_json()

        assert error["type"] == "error"
        assert error["request_id"] == "bad-typing"
        assert error["code"] == "invalid_typing"
