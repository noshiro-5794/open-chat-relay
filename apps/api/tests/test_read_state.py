from httpx import AsyncClient


async def auth_headers(client: AsyncClient, email: str = "owner@example.com") -> dict[str, str]:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "Owner",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_room(client: AsyncClient, headers: dict[str, str]) -> dict:
    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Read State Team"},
        headers=headers,
    )
    workspace_id = workspace_response.json()["id"]
    room_response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "General"},
        headers=headers,
    )
    assert room_response.status_code == 201
    return room_response.json()


async def send_message(
    client: AsyncClient, headers: dict[str, str], room_id: str, content: str
) -> dict:
    response = await client.post(
        f"/v1/rooms/{room_id}/messages",
        json={"content": content},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_update_room_read_state_creates_durable_event(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    await send_message(client, headers, room["id"], "one")
    await send_message(client, headers, room["id"], "two")

    response = await client.put(
        f"/v1/rooms/{room['id']}/read-state",
        json={"last_read_event_seq": 2},
        headers=headers,
    )

    assert response.status_code == 200
    read_state = response.json()
    assert read_state["room_id"] == room["id"]
    assert read_state["last_read_event_seq"] == 2

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    events = events_response.json()
    assert [event["type"] for event in events] == [
        "message.created",
        "message.created",
        "room.read_state_updated",
    ]
    assert events[2]["room_event_seq"] == 3
    assert events[2]["actor_type"] == "user"
    assert events[2]["data"]["last_read_event_seq"] == 2
    assert events[2]["data"]["user_id"] == read_state["user_id"]


async def test_room_read_state_is_monotonic_and_idempotent(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    await send_message(client, headers, room["id"], "one")
    await send_message(client, headers, room["id"], "two")

    first_response = await client.put(
        f"/v1/rooms/{room['id']}/read-state",
        json={"last_read_event_seq": 2},
        headers=headers,
    )
    second_response = await client.put(
        f"/v1/rooms/{room['id']}/read-state",
        json={"last_read_event_seq": 1},
        headers=headers,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["last_read_event_seq"] == 2

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    assert [event["type"] for event in events_response.json()].count("room.read_state_updated") == 1


async def test_room_read_state_cannot_point_beyond_latest_event(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    await send_message(client, headers, room["id"], "one")

    response = await client.put(
        f"/v1/rooms/{room['id']}/read-state",
        json={"last_read_event_seq": 99},
        headers=headers,
    )

    assert response.status_code == 400


async def test_list_room_read_states_returns_existing_states(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    await send_message(client, headers, room["id"], "one")
    await client.put(
        f"/v1/rooms/{room['id']}/read-state",
        json={"last_read_event_seq": 1},
        headers=headers,
    )

    response = await client.get(f"/v1/rooms/{room['id']}/read-states", headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["last_read_event_seq"] == 1
