from starlette.testclient import TestClient


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/v1/auth/register",
        json={
            "email": "presence@example.com",
            "password": "correct horse battery staple",
            "display_name": "Presence",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_room(client: TestClient, headers: dict[str, str]) -> dict:
    workspace_response = client.post(
        "/v1/workspaces",
        json={"name": "Presence Team"},
        headers=headers,
    )
    workspace_id = workspace_response.json()["id"]
    room_response = client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "General"},
        headers=headers,
    )
    return room_response.json()


def test_room_presence_lists_subscribed_users(sync_client: TestClient) -> None:
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
        assert websocket.receive_json()["type"] == "ack"

        response = sync_client.get(f"/v1/rooms/{room['id']}/presence", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["room_id"] == room["id"]
    assert len(body["users"]) == 1
    assert body["users"][0]["status"] == "online"


def test_presence_update_broadcasts_ephemeral_signal(sync_client: TestClient) -> None:
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
                "type": "presence.update",
                "request_id": "presence-1",
                "data": {"room_id": room["id"], "status": "away"},
            }
        )

        assert sender.receive_json()["type"] == "ack"
        event = listener.receive_json()
        assert event["type"] == "presence.updated"
        assert event["delivery"]["lane"] == "signal"
        assert event["data"]["status"] == "away"

        response = sync_client.get(f"/v1/rooms/{room['id']}/presence", headers=headers)
        assert response.status_code == 200
        assert response.json()["users"][0]["status"] == "away"


def test_room_presence_clears_user_after_disconnect(sync_client: TestClient) -> None:
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
        assert websocket.receive_json()["type"] == "ack"

    response = sync_client.get(f"/v1/rooms/{room['id']}/presence", headers=headers)

    assert response.status_code == 200
    assert response.json()["users"] == []
