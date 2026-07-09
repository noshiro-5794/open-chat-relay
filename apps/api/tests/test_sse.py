from httpx import AsyncClient


async def auth_headers(client: AsyncClient, email: str = "sse@example.com") -> dict[str, str]:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "SSE",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_room(client: AsyncClient, headers: dict[str, str]) -> dict:
    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "SSE Team"},
        headers=headers,
    )
    workspace_id = workspace_response.json()["id"]
    room_response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "General"},
        headers=headers,
    )
    return room_response.json()


async def create_message(
    client: AsyncClient,
    headers: dict[str, str],
    room_id: str,
    content: str,
) -> None:
    response = await client.post(
        f"/v1/rooms/{room_id}/messages",
        json={"content": content},
        headers=headers,
    )
    assert response.status_code == 201


async def test_sse_stream_replays_missed_events_with_header_auth(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    await create_message(client, headers, room["id"], "one")
    await create_message(client, headers, room["id"], "two")

    response = await client.get(
        f"/v1/rooms/{room['id']}/events/stream?last_event_seq=1&once=true",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 2" in response.text
    assert "event: message.created" in response.text
    assert "two" in response.text
    assert "one" not in response.text


async def test_sse_stream_supports_query_token(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    token = headers["Authorization"].removeprefix("Bearer ")
    room = await create_room(client, headers)
    await create_message(client, headers, room["id"], "hello query token")

    response = await client.get(
        f"/v1/rooms/{room['id']}/events/stream?token={token}&once=true",
    )

    assert response.status_code == 200
    assert "hello query token" in response.text


async def test_sse_stream_requires_room_membership(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)

    leave_response = await client.post(f"/v1/rooms/{room['id']}/leave", headers=headers)
    assert leave_response.status_code == 200

    response = await client.get(f"/v1/rooms/{room['id']}/events/stream?once=true", headers=headers)

    assert response.status_code == 403
