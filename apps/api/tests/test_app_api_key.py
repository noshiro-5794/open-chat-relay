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
        json={"name": "Developer Team"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def create_app(client: AsyncClient, headers: dict[str, str], workspace_id: str) -> dict:
    response = await client.post(
        f"/v1/workspaces/{workspace_id}/apps",
        json={"name": "GitHub Bot"},
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


async def create_api_key(client: AsyncClient, headers: dict[str, str], app_id: str) -> dict:
    response = await client.post(
        f"/v1/apps/{app_id}/api-keys",
        json={"name": "CI"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def test_create_and_list_workspace_apps(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    workspace = await create_workspace(client, headers)

    app = await create_app(client, headers, workspace["id"])
    list_response = await client.get(f"/v1/workspaces/{workspace['id']}/apps", headers=headers)

    assert app["name"] == "GitHub Bot"
    assert app["slug"] == "github-bot"
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == app["id"]


async def test_duplicate_app_slug_is_rejected(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    workspace = await create_workspace(client, headers)

    first_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/apps",
        json={"name": "Bot", "slug": "bot"},
        headers=headers,
    )
    second_response = await client.post(
        f"/v1/workspaces/{workspace['id']}/apps",
        json={"name": "Other Bot", "slug": "bot"},
        headers=headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


async def test_create_list_and_revoke_api_key(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    workspace = await create_workspace(client, headers)
    app = await create_app(client, headers, workspace["id"])

    create_response = await client.post(
        f"/v1/apps/{app['id']}/api-keys",
        json={"name": "CI"},
        headers=headers,
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["secret"].startswith("ocr_sk_")
    assert created["api_key"]["key_prefix"] == created["secret"][:16]

    list_response = await client.get(f"/v1/apps/{app['id']}/api-keys", headers=headers)
    listed_key = list_response.json()[0]
    assert "secret" not in listed_key
    assert listed_key["id"] == created["api_key"]["id"]
    assert listed_key["revoked_at"] is None

    revoke_response = await client.post(
        f"/v1/apps/{app['id']}/api-keys/{created['api_key']['id']}/revoke",
        headers=headers,
    )

    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked_at"] is not None


async def test_api_key_can_send_message(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    workspace = await create_workspace(client, headers)
    room = await create_room(client, headers, workspace["id"])
    app = await create_app(client, headers, workspace["id"])
    created_key = await create_api_key(client, headers, app["id"])
    api_headers = {"Authorization": f"Bearer {created_key['secret']}"}

    response = await client.post(
        f"/v1/app/rooms/{room['id']}/messages",
        json={"content": "hello from api key"},
        headers=api_headers,
    )

    assert response.status_code == 201
    message = response.json()
    assert message["content"] == "hello from api key"
    assert message["sender_type"] == "bot"
    assert message["sender_id"] is None
    assert message["sender_bot_id"] is not None

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    event = events_response.json()[0]
    assert event["type"] == "message.created"
    assert event["actor_type"] == "bot"
    assert event["actor_id"] is None
    assert event["actor_bot_id"] == message["sender_bot_id"]
    assert event["data"]["content"] == "hello from api key"
    assert event["data"]["sender_type"] == "bot"
    assert event["data"]["sender_bot_id"] == message["sender_bot_id"]


async def test_revoked_api_key_cannot_send_message(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    workspace = await create_workspace(client, headers)
    room = await create_room(client, headers, workspace["id"])
    app = await create_app(client, headers, workspace["id"])
    created_key = await create_api_key(client, headers, app["id"])

    revoke_response = await client.post(
        f"/v1/apps/{app['id']}/api-keys/{created_key['api_key']['id']}/revoke",
        headers=headers,
    )
    response = await client.post(
        f"/v1/app/rooms/{room['id']}/messages",
        json={"content": "nope"},
        headers={"Authorization": f"Bearer {created_key['secret']}"},
    )

    assert revoke_response.status_code == 200
    assert response.status_code == 401
