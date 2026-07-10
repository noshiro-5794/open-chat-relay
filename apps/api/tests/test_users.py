from httpx import AsyncClient


async def register_user(
    client: AsyncClient,
    *,
    email: str,
    display_name: str,
) -> dict:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": display_name,
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_user_can_update_profile(client: AsyncClient) -> None:
    auth = await register_user(
        client,
        email="profile@example.com",
        display_name="Before",
    )

    response = await client.patch(
        "/v1/me",
        json={"display_name": "After"},
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "After"


async def test_users_directory_lists_active_users(client: AsyncClient) -> None:
    auth = await register_user(
        client,
        email="alice@example.com",
        display_name="Alice",
    )
    await register_user(
        client,
        email="bob@example.com",
        display_name="Bob",
    )

    response = await client.get(
        "/v1/users?q=bo",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )

    assert response.status_code == 200
    assert [user["email"] for user in response.json()] == ["bob@example.com"]
