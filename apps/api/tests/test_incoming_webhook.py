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


async def create_workspace(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        "/v1/workspaces",
        json={"name": "Webhook Team"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def create_room(client: AsyncClient, headers: dict[str, str], workspace_id: str) -> dict:
    response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "Deployments"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def create_app(client: AsyncClient, headers: dict[str, str], workspace_id: str) -> dict:
    response = await client.post(
        f"/v1/workspaces/{workspace_id}/apps",
        json={"name": "Deploy Bot"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def create_incoming_webhook(
    client: AsyncClient,
    headers: dict[str, str],
    app_id: str,
    room_id: str,
) -> dict:
    response = await client.post(
        f"/v1/apps/{app_id}/incoming-webhooks",
        json={"name": "Deploy Events", "room_id": room_id},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_incoming_webhook_can_deliver_bot_message(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    workspace = await create_workspace(client, headers)
    room = await create_room(client, headers, workspace["id"])
    app = await create_app(client, headers, workspace["id"])
    created = await create_incoming_webhook(client, headers, app["id"], room["id"])

    list_response = await client.get(f"/v1/apps/{app['id']}/incoming-webhooks", headers=headers)
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == created["webhook"]["id"]
    assert "secret" not in list_response.json()[0]

    deliver_response = await client.post(
        created["delivery_url"],
        json={
            "content": "deploy succeeded",
            "external_id": "deploy-123",
            "source": "ci",
            "metadata": {"commit": "abc123"},
        },
        headers={"Authorization": f"Bearer {created['secret']}"},
    )

    assert deliver_response.status_code == 202
    message = deliver_response.json()
    assert message["content"] == "deploy succeeded"
    assert message["sender_type"] == "bot"
    assert message["sender_bot_id"] == created["webhook"]["bot_id"]

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    event = events_response.json()[0]
    assert event["type"] == "message.created"
    assert event["actor_type"] == "bot"
    assert event["actor_bot_id"] == created["webhook"]["bot_id"]
    assert event["data"]["metadata"]["webhook_id"] == created["webhook"]["id"]
    assert event["data"]["metadata"]["external_id"] == "deploy-123"
    assert event["data"]["metadata"]["source"] == "ci"
    assert event["data"]["metadata"]["payload"] == {"commit": "abc123"}


async def test_revoked_incoming_webhook_cannot_deliver(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    workspace = await create_workspace(client, headers)
    room = await create_room(client, headers, workspace["id"])
    app = await create_app(client, headers, workspace["id"])
    created = await create_incoming_webhook(client, headers, app["id"], room["id"])

    revoke_response = await client.post(
        f"/v1/apps/{app['id']}/incoming-webhooks/{created['webhook']['id']}/revoke",
        headers=headers,
    )
    deliver_response = await client.post(
        created["delivery_url"],
        json={"content": "should not arrive"},
        headers={"Authorization": f"Bearer {created['secret']}"},
    )

    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked_at"] is not None
    assert deliver_response.status_code == 401


async def test_incoming_webhook_rejects_wrong_secret(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    workspace = await create_workspace(client, headers)
    room = await create_room(client, headers, workspace["id"])
    app = await create_app(client, headers, workspace["id"])
    created = await create_incoming_webhook(client, headers, app["id"], room["id"])

    response = await client.post(
        created["delivery_url"],
        json={"content": "nope"},
        headers={"Authorization": "Bearer wrong-secret"},
    )

    assert response.status_code == 401
