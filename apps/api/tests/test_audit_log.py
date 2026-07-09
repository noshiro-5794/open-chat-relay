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
        json={"name": "Audit Team"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def create_room(client: AsyncClient, headers: dict[str, str], workspace_id: str) -> dict:
    response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "Audit Room"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_workspace_owner_can_read_audit_logs(client: AsyncClient) -> None:
    owner_headers = await auth_headers(
        client,
        email="owner@example.com",
        display_name="Owner",
    )
    await auth_headers(client, email="member@example.com", display_name="Member")
    workspace = await create_workspace(client, owner_headers)
    room = await create_room(client, owner_headers, workspace["id"])

    member_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com"},
        headers=owner_headers,
    )
    app_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/apps",
        json={"name": "Audit Bot"},
        headers=owner_headers,
    )
    api_key_response = await client.post(
        f"/v1/apps/{app_response.json()['id']}/api-keys",
        json={"name": "CI"},
        headers=owner_headers,
    )
    webhook_response = await client.post(
        f"/v1/apps/{app_response.json()['id']}/incoming-webhooks",
        json={"name": "Deploys", "room_id": room["id"]},
        headers=owner_headers,
    )
    await client.post(
        f"/v1/rooms/{room['id']}/members",
        json={"user_id": member_response.json()["user_id"]},
        headers=owner_headers,
    )
    await client.post(
        f"/v1/apps/{app_response.json()['id']}/api-keys/"
        f"{api_key_response.json()['api_key']['id']}/revoke",
        headers=owner_headers,
    )
    await client.post(
        f"/v1/apps/{app_response.json()['id']}/incoming-webhooks/"
        f"{webhook_response.json()['webhook']['id']}/revoke",
        headers=owner_headers,
    )

    response = await client.get(
        f"/v1/workspaces/{workspace['id']}/audit-logs",
        headers=owner_headers,
    )

    assert response.status_code == 200
    actions = {item["action"] for item in response.json()}
    assert {
        "workspace.member_upserted",
        "app.created",
        "api_key.created",
        "incoming_webhook.created",
        "room.member_upserted",
        "api_key.revoked",
        "incoming_webhook.revoked",
    }.issubset(actions)


async def test_workspace_member_cannot_read_audit_logs(client: AsyncClient) -> None:
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
    add_member_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/members",
        json={"email": "member@example.com"},
        headers=owner_headers,
    )

    response = await client.get(
        f"/v1/workspaces/{workspace['id']}/audit-logs",
        headers=member_headers,
    )

    assert add_member_response.status_code == 201
    assert response.status_code == 403
