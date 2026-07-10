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


async def test_add_friend_creates_mutual_contact(client: AsyncClient) -> None:
    alice_headers = await auth_headers(
        client,
        email="alice-friend@example.com",
        display_name="Alice",
    )
    bob_headers = await auth_headers(
        client,
        email="bob-friend@example.com",
        display_name="Bob",
    )

    add_response = await client.post(
        "/v1/friends",
        json={"email": "bob-friend@example.com"},
        headers=alice_headers,
    )
    assert add_response.status_code == 201
    assert add_response.json()["email"] == "bob-friend@example.com"

    alice_friends_response = await client.get("/v1/friends", headers=alice_headers)
    bob_friends_response = await client.get("/v1/friends", headers=bob_headers)

    assert [friend["email"] for friend in alice_friends_response.json()] == [
        "bob-friend@example.com"
    ]
    assert [friend["email"] for friend in bob_friends_response.json()] == [
        "alice-friend@example.com"
    ]


async def test_direct_conversation_creates_mutual_contact(client: AsyncClient) -> None:
    alice_headers = await auth_headers(
        client,
        email="alice-direct-friend@example.com",
        display_name="Alice",
    )
    bob_headers = await auth_headers(
        client,
        email="bob-direct-friend@example.com",
        display_name="Bob",
    )
    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Friend Team"},
        headers=alice_headers,
    )
    assert workspace_response.status_code == 201

    direct_response = await client.post(
        f"/v1/workspaces/{workspace_response.json()['id']}/rooms/direct",
        json={"email": "bob-direct-friend@example.com"},
        headers=alice_headers,
    )
    assert direct_response.status_code == 201

    bob_friends_response = await client.get("/v1/friends", headers=bob_headers)
    assert bob_friends_response.status_code == 200
    assert [friend["email"] for friend in bob_friends_response.json()] == [
        "alice-direct-friend@example.com"
    ]
