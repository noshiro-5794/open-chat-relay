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
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_global_direct_conversation_is_visible_to_both_users(
    client: AsyncClient,
) -> None:
    alice_headers = await auth_headers(
        client,
        email="alice-global-direct@example.com",
        display_name="Alice",
    )
    bob_headers = await auth_headers(
        client,
        email="bob-global-direct@example.com",
        display_name="Bob",
    )

    direct_response = await client.post(
        "/v1/conversations/direct",
        json={"email": "bob-global-direct@example.com"},
        headers=alice_headers,
    )
    assert direct_response.status_code == 201
    room = direct_response.json()
    assert room["is_private"] is True

    alice_conversations_response = await client.get(
        "/v1/conversations",
        headers=alice_headers,
    )
    bob_conversations_response = await client.get(
        "/v1/conversations",
        headers=bob_headers,
    )

    assert alice_conversations_response.status_code == 200
    assert bob_conversations_response.status_code == 200
    assert [
        conversation["id"] for conversation in alice_conversations_response.json()["conversations"]
    ] == [room["id"]]
    assert [
        conversation["id"] for conversation in bob_conversations_response.json()["conversations"]
    ] == [room["id"]]

    message_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "hello from alice"},
        headers=alice_headers,
    )
    assert message_response.status_code == 201

    bob_messages_response = await client.get(
        f"/v1/rooms/{room['id']}/messages",
        headers=bob_headers,
    )
    assert bob_messages_response.status_code == 200
    assert [message["content"] for message in bob_messages_response.json()] == ["hello from alice"]

    bob_reply_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "hello from bob"},
        headers=bob_headers,
    )
    assert bob_reply_response.status_code == 201

    alice_messages_response = await client.get(
        f"/v1/rooms/{room['id']}/messages",
        headers=alice_headers,
    )
    assert alice_messages_response.status_code == 200
    assert [message["content"] for message in alice_messages_response.json()] == [
        "hello from alice",
        "hello from bob",
    ]


async def test_global_group_conversation_is_visible_to_invited_members(
    client: AsyncClient,
) -> None:
    alice_headers = await auth_headers(
        client,
        email="alice-global-group@example.com",
        display_name="Alice",
    )
    bob_headers = await auth_headers(
        client,
        email="bob-global-group@example.com",
        display_name="Bob",
    )
    await auth_headers(
        client,
        email="carol-global-group@example.com",
        display_name="Carol",
    )

    group_response = await client.post(
        "/v1/conversations/groups",
        json={
            "name": "Launch Group",
            "member_emails": [
                "bob-global-group@example.com",
                "carol-global-group@example.com",
            ],
        },
        headers=alice_headers,
    )
    assert group_response.status_code == 201
    group = group_response.json()
    assert group["is_private"] is False

    bob_conversations_response = await client.get(
        "/v1/conversations",
        headers=bob_headers,
    )
    assert bob_conversations_response.status_code == 200
    assert [
        conversation["id"] for conversation in bob_conversations_response.json()["conversations"]
    ] == [group["id"]]

    members_response = await client.get(
        f"/v1/rooms/{group['id']}/members",
        headers=alice_headers,
    )
    assert members_response.status_code == 200
    assert sorted(member["email"] for member in members_response.json()) == [
        "alice-global-group@example.com",
        "bob-global-group@example.com",
        "carol-global-group@example.com",
    ]


async def test_global_conversations_do_not_list_legacy_workspace_rooms(
    client: AsyncClient,
) -> None:
    headers = await auth_headers(
        client,
        email="legacy-filter@example.com",
        display_name="Legacy User",
    )

    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Legacy Workspace"},
        headers=headers,
    )
    assert workspace_response.status_code == 201
    legacy_room_response = await client.post(
        f"/v1/workspaces/{workspace_response.json()['id']}/rooms",
        json={"name": "Legacy General"},
        headers=headers,
    )
    assert legacy_room_response.status_code == 201

    conversations_response = await client.get("/v1/conversations", headers=headers)

    assert conversations_response.status_code == 200
    assert conversations_response.json()["conversations"] == []


async def test_global_group_names_can_repeat(client: AsyncClient) -> None:
    headers = await auth_headers(
        client,
        email="repeat-group-name@example.com",
        display_name="Repeat User",
    )

    first_response = await client.post(
        "/v1/conversations/groups",
        json={"name": "Project Group", "member_emails": []},
        headers=headers,
    )
    second_response = await client.post(
        "/v1/conversations/groups",
        json={"name": "Project Group", "member_emails": []},
        headers=headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["id"] != second_response.json()["id"]
    assert first_response.json()["name"] == "Project Group"
    assert second_response.json()["name"] == "Project Group"
