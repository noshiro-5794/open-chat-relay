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
        json={"name": "Members Team"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def create_room(client: AsyncClient, headers: dict[str, str], workspace_id: str) -> dict:
    response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "General"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_workspace_owner_can_add_workspace_member(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    await auth_headers(client, email="member@example.com", display_name="Member")
    workspace = await create_workspace(client, owner_headers)

    response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com", "role": "member"},
        headers=owner_headers,
    )
    list_response = await client.get(
        f"/v1/workspaces/{workspace['id']}/members",
        headers=owner_headers,
    )

    assert response.status_code == 201
    member = response.json()
    assert member["email"] == "member@example.com"
    assert member["role"] == "member"
    assert {item["email"] for item in list_response.json()} == {
        "owner@example.com",
        "member@example.com",
    }


async def test_workspace_member_cannot_manage_workspace_members(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    member_headers = await auth_headers(
        client,
        email="member@example.com",
        display_name="Member",
    )
    await auth_headers(client, email="other@example.com", display_name="Other")
    workspace = await create_workspace(client, owner_headers)
    add_member_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com"},
        headers=owner_headers,
    )

    response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "other@example.com"},
        headers=member_headers,
    )

    assert add_member_response.status_code == 201
    assert response.status_code == 403


async def test_workspace_owner_can_update_workspace_member_role(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    await auth_headers(client, email="member@example.com", display_name="Member")
    workspace = await create_workspace(client, owner_headers)
    add_member_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com"},
        headers=owner_headers,
    )

    response = await client.patch(
        f"/v1/workspaces/{workspace['id']}/members/{add_member_response.json()['user_id']}",
        json={"role": "owner"},
        headers=owner_headers,
    )

    assert response.status_code == 200
    assert response.json()["email"] == "member@example.com"
    assert response.json()["role"] == "owner"


async def test_workspace_must_keep_at_least_one_owner(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    workspace = await create_workspace(client, owner_headers)
    members_response = await client.get(
        f"/v1/workspaces/{workspace['id']}/members",
        headers=owner_headers,
    )
    owner_member = members_response.json()[0]

    demote_response = await client.patch(
        f"/v1/workspaces/{workspace['id']}/members/{owner_member['user_id']}",
        json={"role": "member"},
        headers=owner_headers,
    )
    remove_response = await client.delete(
        f"/v1/workspaces/{workspace['id']}/members/{owner_member['user_id']}",
        headers=owner_headers,
    )

    assert demote_response.status_code == 409
    assert demote_response.json()["detail"] == "Workspace must keep at least one owner."
    assert remove_response.status_code == 409
    assert remove_response.json()["detail"] == "Workspace must keep at least one owner."


async def test_remove_workspace_member_revokes_room_membership(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    member_headers = await auth_headers(
        client,
        email="member@example.com",
        display_name="Member",
    )
    workspace = await create_workspace(client, owner_headers)
    room = await create_room(client, owner_headers, workspace["id"])
    workspace_member_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com"},
        headers=owner_headers,
    )
    await client.post(
        f"/v1/rooms/{room['id']}/members",
        json={"user_id": workspace_member_response.json()["user_id"]},
        headers=owner_headers,
    )

    remove_response = await client.delete(
        f"/v1/workspaces/{workspace['id']}/members/{workspace_member_response.json()['user_id']}",
        headers=owner_headers,
    )
    message_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "should fail"},
        headers=member_headers,
    )
    room_members_response = await client.get(
        f"/v1/rooms/{room['id']}/members",
        headers=owner_headers,
    )

    assert remove_response.status_code == 204
    assert message_response.status_code == 404
    assert {member["email"] for member in room_members_response.json()} == {"owner@example.com"}


async def test_room_owner_can_add_workspace_member_to_room(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    member_headers = await auth_headers(
        client,
        email="member@example.com",
        display_name="Member",
    )
    workspace = await create_workspace(client, owner_headers)
    room = await create_room(client, owner_headers, workspace["id"])
    workspace_member_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com"},
        headers=owner_headers,
    )

    room_member_response = await client.post(
        f"/v1/rooms/{room['id']}/members",
        json={"user_id": workspace_member_response.json()["user_id"]},
        headers=owner_headers,
    )
    message_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "hello from member"},
        headers=member_headers,
    )

    assert room_member_response.status_code == 201
    assert room_member_response.json()["email"] == "member@example.com"
    assert message_response.status_code == 201
    assert message_response.json()["content"] == "hello from member"


async def test_room_owner_can_update_room_member_role(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    await auth_headers(client, email="member@example.com", display_name="Member")
    workspace = await create_workspace(client, owner_headers)
    room = await create_room(client, owner_headers, workspace["id"])
    workspace_member_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com"},
        headers=owner_headers,
    )
    room_member_response = await client.post(
        f"/v1/rooms/{room['id']}/members",
        json={"user_id": workspace_member_response.json()["user_id"]},
        headers=owner_headers,
    )

    response = await client.patch(
        f"/v1/rooms/{room['id']}/members/{room_member_response.json()['user_id']}",
        json={"role": "owner"},
        headers=owner_headers,
    )

    assert response.status_code == 200
    assert response.json()["email"] == "member@example.com"
    assert response.json()["role"] == "owner"


async def test_room_must_keep_at_least_one_owner(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    workspace = await create_workspace(client, owner_headers)
    room = await create_room(client, owner_headers, workspace["id"])
    members_response = await client.get(f"/v1/rooms/{room['id']}/members", headers=owner_headers)
    owner_member = members_response.json()[0]

    demote_response = await client.patch(
        f"/v1/rooms/{room['id']}/members/{owner_member['user_id']}",
        json={"role": "member"},
        headers=owner_headers,
    )
    remove_response = await client.delete(
        f"/v1/rooms/{room['id']}/members/{owner_member['user_id']}",
        headers=owner_headers,
    )

    assert demote_response.status_code == 409
    assert demote_response.json()["detail"] == "Room must keep at least one owner."
    assert remove_response.status_code == 409
    assert remove_response.json()["detail"] == "Room must keep at least one owner."


async def test_remove_room_member_revokes_room_access(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    member_headers = await auth_headers(
        client,
        email="member@example.com",
        display_name="Member",
    )
    workspace = await create_workspace(client, owner_headers)
    room = await create_room(client, owner_headers, workspace["id"])
    workspace_member_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com"},
        headers=owner_headers,
    )
    await client.post(
        f"/v1/rooms/{room['id']}/members",
        json={"user_id": workspace_member_response.json()["user_id"]},
        headers=owner_headers,
    )

    remove_response = await client.delete(
        f"/v1/rooms/{room['id']}/members/{workspace_member_response.json()['user_id']}",
        headers=owner_headers,
    )
    message_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "should fail"},
        headers=member_headers,
    )

    assert remove_response.status_code == 204
    assert message_response.status_code == 403


async def test_room_member_must_first_belong_to_workspace(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    outsider_headers = await auth_headers(
        client,
        email="outsider@example.com",
        display_name="Outsider",
    )
    workspace = await create_workspace(client, owner_headers)
    room = await create_room(client, owner_headers, workspace["id"])
    outsider_profile = await client.get("/v1/me", headers=outsider_headers)

    response = await client.post(
        f"/v1/rooms/{room['id']}/members",
        json={"user_id": outsider_profile.json()["id"]},
        headers=owner_headers,
    )

    assert response.status_code == 409
