from httpx import AsyncClient


async def register(
    client: AsyncClient,
    *,
    email: str,
    display_name: str,
) -> tuple[dict[str, str], dict]:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": display_name,
        },
    )
    body = response.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


async def test_message_creates_notification_for_other_room_members(client: AsyncClient) -> None:
    owner_headers, _owner = await register(
        client,
        email="notify-owner@example.com",
        display_name="Notify Owner",
    )
    member_headers, member = await register(
        client,
        email="notify-member@example.com",
        display_name="Notify Member",
    )
    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Notify Team"},
        headers=owner_headers,
    )
    workspace = workspace_response.json()
    room_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/rooms",
        json={"name": "General"},
        headers=owner_headers,
    )
    room = room_response.json()
    await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "notify-member@example.com"},
        headers=owner_headers,
    )
    await client.post(
        f"/v1/rooms/{room['id']}/members",
        json={"user_id": member["id"]},
        headers=owner_headers,
    )

    message_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "notification payload"},
        headers=owner_headers,
    )
    member_notifications_response = await client.get("/v1/notifications", headers=member_headers)
    unread_count_response = await client.get(
        "/v1/notifications/unread-count",
        headers=member_headers,
    )
    owner_notifications_response = await client.get("/v1/notifications", headers=owner_headers)

    assert message_response.status_code == 201
    assert member_notifications_response.status_code == 200
    notifications = member_notifications_response.json()
    assert len(notifications) == 1
    assert notifications[0]["notification_type"] == "message.created"
    assert notifications[0]["title"] == "New message from Notify Owner"
    assert notifications[0]["body"] == "notification payload"
    assert notifications[0]["payload"]["message_id"] == message_response.json()["id"]
    assert unread_count_response.json() == {"unread_count": 1}
    assert owner_notifications_response.json() == []


async def test_notifications_can_be_marked_read(client: AsyncClient) -> None:
    owner_headers, _owner = await register(
        client,
        email="read-owner@example.com",
        display_name="Read Owner",
    )
    member_headers, member = await register(
        client,
        email="read-member@example.com",
        display_name="Read Member",
    )
    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Read Team"},
        headers=owner_headers,
    )
    workspace = workspace_response.json()
    room_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/rooms",
        json={"name": "General"},
        headers=owner_headers,
    )
    room = room_response.json()
    await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "read-member@example.com"},
        headers=owner_headers,
    )
    await client.post(
        f"/v1/rooms/{room['id']}/members",
        json={"user_id": member["id"]},
        headers=owner_headers,
    )
    await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "read me"},
        headers=owner_headers,
    )
    notifications = (await client.get("/v1/notifications", headers=member_headers)).json()

    mark_response = await client.post(
        f"/v1/notifications/{notifications[0]['id']}/read",
        headers=member_headers,
    )
    unread_response = await client.get(
        "/v1/notifications?unread_only=true",
        headers=member_headers,
    )
    unread_count_response = await client.get(
        "/v1/notifications/unread-count",
        headers=member_headers,
    )
    read_all_response = await client.post("/v1/notifications/read-all", headers=member_headers)

    assert mark_response.status_code == 200
    assert mark_response.json()["read_at"] is not None
    assert unread_response.json() == []
    assert unread_count_response.json() == {"unread_count": 0}
    assert read_all_response.json() == {"updated": 0}
