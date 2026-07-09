from httpx import AsyncClient


async def test_register_login_and_me(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "Aki@example.com",
            "password": "correct horse battery staple",
            "display_name": "Aki",
        },
    )

    assert register_response.status_code == 201
    register_body = register_response.json()
    assert register_body["token_type"] == "bearer"  # noqa: S105
    assert register_body["access_token"]
    assert register_body["refresh_token"]
    assert register_body["user"]["email"] == "aki@example.com"
    assert register_body["user"]["is_system_admin"] is True

    me_response = await client.get(
        "/v1/me",
        headers={"Authorization": f"Bearer {register_body['access_token']}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "aki@example.com"

    login_response = await client.post(
        "/v1/auth/login",
        json={
            "email": "aki@example.com",
            "password": "correct horse battery staple",
        },
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["display_name"] == "Aki"


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    payload = {
        "email": "duplicate@example.com",
        "password": "correct horse battery staple",
        "display_name": "Aki",
    }

    first_response = await client.post("/v1/auth/register", json=payload)
    second_response = await client.post("/v1/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


async def test_login_rejects_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "correct horse battery staple",
            "display_name": "Aki",
        },
    )

    response = await client.post(
        "/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": "wrong password",
        },
    )

    assert response.status_code == 401


async def test_refresh_issues_new_token_pair(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "password": "correct horse battery staple",
            "display_name": "Aki",
        },
    )
    refresh_token = register_response.json()["refresh_token"]

    response = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_refresh_token_is_rotated_after_use(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "rotate@example.com",
            "password": "correct horse battery staple",
            "display_name": "Aki",
        },
    )
    refresh_token = register_response.json()["refresh_token"]

    first_refresh_response = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    second_refresh_response = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert first_refresh_response.status_code == 200
    assert first_refresh_response.json()["refresh_token"] != refresh_token
    assert second_refresh_response.status_code == 401


async def test_auth_sessions_can_be_listed_and_revoked(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "sessions@example.com",
            "password": "correct horse battery staple",
            "display_name": "Aki",
        },
    )
    body = register_response.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    list_response = await client.get("/v1/auth/sessions", headers=headers)
    session_id = list_response.json()[0]["id"]
    revoke_response = await client.delete(f"/v1/auth/sessions/{session_id}", headers=headers)
    refresh_response = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )
    list_after_revoke_response = await client.get("/v1/auth/sessions", headers=headers)

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert revoke_response.status_code == 204
    assert refresh_response.status_code == 401
    assert list_after_revoke_response.json() == []


async def test_logout_revokes_refresh_token_when_provided(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "logout@example.com",
            "password": "correct horse battery staple",
            "display_name": "Aki",
        },
    )
    body = register_response.json()

    logout_response = await client.post(
        "/v1/auth/logout",
        json={"refresh_token": body["refresh_token"]},
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    refresh_response = await client.post(
        "/v1/auth/refresh",
        json={"refresh_token": body["refresh_token"]},
    )

    assert logout_response.status_code == 200
    assert logout_response.json()["status"] == "ok"
    assert refresh_response.status_code == 401
