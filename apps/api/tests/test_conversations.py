from httpx import AsyncClient


async def auth_headers(
    client: AsyncClient,
    *,
    email: str,
    display_name: str,
) -> dict[str, str]:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": display_name,
        },
    )
    assert response.status_code == 201
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_workspace(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        "/v1/workspaces",
        json={"name": "Conversation Team"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def create_room(client: AsyncClient, headers: dict[str, str], workspace_id: str) -> dict:
    response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "Project Room"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_direct_conversation_adds_both_users_to_same_room(
    client: AsyncClient,
) -> None:
    alice_headers = await auth_headers(
        client,
        email="alice-direct@example.com",
        display_name="Alice",
    )
    bob_headers = await auth_headers(
        client,
        email="bob-direct@example.com",
        display_name="Bob",
    )
    workspace = await create_workspace(client, alice_headers)

    direct_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/rooms/direct",
        json={"email": "bob-direct@example.com"},
        headers=alice_headers,
    )

    assert direct_response.status_code == 201
    direct_room = direct_response.json()
    assert direct_room["is_private"] is True
    assert direct_room["role"] == "owner"

    bob_workspaces_response = await client.get("/v1/workspaces", headers=bob_headers)
    assert bob_workspaces_response.status_code == 200
    assert [item["id"] for item in bob_workspaces_response.json()] == [workspace["id"]]

    bob_rooms_response = await client.get(
        f"/v1/workspaces/{workspace['id']}/rooms",
        headers=bob_headers,
    )
    assert bob_rooms_response.status_code == 200
    bob_rooms = bob_rooms_response.json()
    assert [(room["id"], room["role"]) for room in bob_rooms] == [(direct_room["id"], "member")]

    bob_message_response = await client.post(
        f"/v1/rooms/{direct_room['id']}/messages",
        json={"content": "hello Alice"},
        headers=bob_headers,
    )
    assert bob_message_response.status_code == 201

    repeated_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/rooms/direct",
        json={"email": "bob-direct@example.com"},
        headers=alice_headers,
    )
    assert repeated_response.status_code == 201
    assert repeated_response.json()["id"] == direct_room["id"]


async def test_one_sided_private_room_is_hidden_from_room_list(client: AsyncClient) -> None:
    alice_headers = await auth_headers(
        client,
        email="alice-stale-direct@example.com",
        display_name="Alice",
    )
    bob_headers = await auth_headers(
        client,
        email="bob-stale-direct@example.com",
        display_name="Bob",
    )
    workspace = await create_workspace(client, alice_headers)
    direct_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/rooms/direct",
        json={"email": "bob-stale-direct@example.com"},
        headers=alice_headers,
    )
    direct_room = direct_response.json()

    leave_response = await client.post(
        f"/v1/rooms/{direct_room['id']}/leave",
        headers=alice_headers,
    )
    assert leave_response.status_code == 200

    bob_rooms_response = await client.get(
        f"/v1/workspaces/{workspace['id']}/rooms",
        headers=bob_headers,
    )
    assert bob_rooms_response.status_code == 200
    assert all(room["id"] != direct_room["id"] for room in bob_rooms_response.json())


async def test_room_invite_adds_user_to_workspace_and_group(
    client: AsyncClient,
) -> None:
    alice_headers = await auth_headers(
        client,
        email="alice-group@example.com",
        display_name="Alice",
    )
    bob_headers = await auth_headers(
        client,
        email="bob-group@example.com",
        display_name="Bob",
    )
    workspace = await create_workspace(client, alice_headers)
    room = await create_room(client, alice_headers, workspace["id"])

    invite_response = await client.post(
        f"/v1/rooms/{room['id']}/invites",
        json={"email": "bob-group@example.com"},
        headers=alice_headers,
    )

    assert invite_response.status_code == 201
    invited_member = invite_response.json()
    assert invited_member["email"] == "bob-group@example.com"
    assert invited_member["role"] == "member"

    bob_rooms_response = await client.get(
        f"/v1/workspaces/{workspace['id']}/rooms",
        headers=bob_headers,
    )
    assert bob_rooms_response.status_code == 200
    assert [(item["id"], item["role"]) for item in bob_rooms_response.json()] == [
        (room["id"], "member")
    ]

    bob_message_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "I can see the group"},
        headers=bob_headers,
    )
    assert bob_message_response.status_code == 201
