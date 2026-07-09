from httpx import AsyncClient


async def auth_headers(client: AsyncClient, email: str = "reaction@example.com") -> dict[str, str]:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "Reaction",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_room(client: AsyncClient, headers: dict[str, str]) -> dict:
    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Reaction Team"},
        headers=headers,
    )
    workspace_id = workspace_response.json()["id"]
    room_response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "General"},
        headers=headers,
    )
    return room_response.json()


async def create_message(client: AsyncClient, headers: dict[str, str], room_id: str) -> dict:
    response = await client.post(
        f"/v1/rooms/{room_id}/messages",
        json={"content": "react to me"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_add_reaction_creates_durable_event(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    message = await create_message(client, headers, room["id"])

    response = await client.post(
        f"/v1/rooms/{room['id']}/messages/{message['id']}/reactions",
        json={"emoji": "+1"},
        headers=headers,
    )

    assert response.status_code == 201
    reaction = response.json()
    assert reaction["emoji"] == "+1"
    assert reaction["message_id"] == message["id"]

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    events = events_response.json()
    assert [event["type"] for event in events] == ["message.created", "message.reaction_added"]
    assert events[1]["data"]["emoji"] == "+1"


async def test_duplicate_reaction_is_rejected(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    message = await create_message(client, headers, room["id"])
    url = f"/v1/rooms/{room['id']}/messages/{message['id']}/reactions"

    first_response = await client.post(url, json={"emoji": "+1"}, headers=headers)
    second_response = await client.post(url, json={"emoji": "+1"}, headers=headers)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


async def test_remove_reaction_creates_durable_event(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    message = await create_message(client, headers, room["id"])
    url = f"/v1/rooms/{room['id']}/messages/{message['id']}/reactions"

    add_response = await client.post(url, json={"emoji": "+1"}, headers=headers)
    remove_response = await client.delete(f"{url}?emoji=%2B1", headers=headers)

    assert add_response.status_code == 201
    assert remove_response.status_code == 200
    assert remove_response.json()["emoji"] == "+1"

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    events = events_response.json()
    assert [event["type"] for event in events] == [
        "message.created",
        "message.reaction_added",
        "message.reaction_removed",
    ]
