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


async def test_workspace_create_list_and_get(client: AsyncClient) -> None:
    headers = await auth_headers(client)

    create_response = await client.post(
        "/v1/workspaces",
        json={"name": "Acme Team"},
        headers=headers,
    )

    assert create_response.status_code == 201
    workspace = create_response.json()
    assert workspace["name"] == "Acme Team"
    assert workspace["slug"] == "acme-team"
    assert workspace["role"] == "owner"

    list_response = await client.get("/v1/workspaces", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == workspace["id"]

    get_response = await client.get(f"/v1/workspaces/{workspace['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["slug"] == "acme-team"


async def test_workspace_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/v1/workspaces", json={"name": "Acme Team"})

    assert response.status_code == 401


async def test_workspace_rejects_duplicate_slug(client: AsyncClient) -> None:
    headers = await auth_headers(client)

    first_response = await client.post(
        "/v1/workspaces",
        json={"name": "Acme Team", "slug": "acme"},
        headers=headers,
    )
    second_response = await client.post(
        "/v1/workspaces",
        json={"name": "Acme Other", "slug": "acme"},
        headers=headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


async def test_room_create_list_get_join_and_leave(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Acme Team"},
        headers=headers,
    )
    workspace_id = workspace_response.json()["id"]

    room_response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "General"},
        headers=headers,
    )

    assert room_response.status_code == 201
    room = room_response.json()
    assert room["slug"] == "general"
    assert room["role"] == "owner"

    list_response = await client.get(f"/v1/workspaces/{workspace_id}/rooms", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == room["id"]

    get_response = await client.get(f"/v1/rooms/{room['id']}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "General"

    leave_response = await client.post(f"/v1/rooms/{room['id']}/leave", headers=headers)
    assert leave_response.status_code == 200
    assert leave_response.json()["room"]["role"] is None

    join_response = await client.post(f"/v1/rooms/{room['id']}/join", headers=headers)
    assert join_response.status_code == 200
    assert join_response.json()["room"]["role"] == "member"


async def test_non_member_cannot_access_workspace_or_room(client: AsyncClient) -> None:
    owner_headers = await auth_headers(client, "owner@example.com")
    stranger_headers = await auth_headers(client, "stranger@example.com")

    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Private Team"},
        headers=owner_headers,
    )
    workspace_id = workspace_response.json()["id"]

    room_response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "Private Room"},
        headers=owner_headers,
    )
    room_id = room_response.json()["id"]

    workspace_get_response = await client.get(
        f"/v1/workspaces/{workspace_id}",
        headers=stranger_headers,
    )
    room_get_response = await client.get(f"/v1/rooms/{room_id}", headers=stranger_headers)

    assert workspace_get_response.status_code == 404
    assert room_get_response.status_code == 404
