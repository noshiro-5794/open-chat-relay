from httpx import AsyncClient


async def test_system_status_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/v1/system/status")

    assert response.status_code == 401


async def test_system_status_reports_core_components(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "system-status@example.com",
            "password": "correct horse battery staple",
            "display_name": "System Status",
        },
    )
    access_token = register_response.json()["access_token"]

    response = await client.get(
        "/v1/system/status",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "OpenChatRelay"
    assert body["environment"] == "test"
    assert body["components"]["database"]["status"] == "ok"
    assert body["components"]["redis"]["status"] == "skipped"
    assert body["components"]["storage"]["status"] == "skipped"
    assert body["components"]["webtransport"]["status"] == "disabled"
    assert body["outbox"] == {"pending": 0, "failed": 0}
    assert body["active_auth_sessions"] == 1


async def test_system_metrics_reports_runtime_counters(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "system-metrics@example.com",
            "password": "correct horse battery staple",
            "display_name": "System Metrics",
        },
    )
    headers = {"Authorization": f"Bearer {register_response.json()['access_token']}"}

    response = await client.get("/v1/system/metrics", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["realtime"] == {
        "active_connections": 0,
        "active_users": 0,
        "subscribed_rooms": 0,
        "room_subscriptions": 0,
    }
    assert body["outbox"] == {"pending": 0, "failed": 0}
    assert body["notifications"] == {"total": 0, "unread": 0}
    assert body["active_auth_sessions"] == 1


async def test_system_status_rejects_non_admin_user(client: AsyncClient) -> None:
    await client.post(
        "/v1/auth/register",
        json={
            "email": "system-admin@example.com",
            "password": "correct horse battery staple",
            "display_name": "System Admin",
        },
    )
    user_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "system-user@example.com",
            "password": "correct horse battery staple",
            "display_name": "System User",
        },
    )
    user_body = user_response.json()

    response = await client.get(
        "/v1/system/status",
        headers={"Authorization": f"Bearer {user_body['access_token']}"},
    )

    assert user_body["user"]["is_system_admin"] is False
    assert response.status_code == 403


async def test_system_metrics_rejects_non_admin_user(client: AsyncClient) -> None:
    await client.post(
        "/v1/auth/register",
        json={
            "email": "metrics-admin@example.com",
            "password": "correct horse battery staple",
            "display_name": "Metrics Admin",
        },
    )
    user_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "metrics-user@example.com",
            "password": "correct horse battery staple",
            "display_name": "Metrics User",
        },
    )
    user_headers = {"Authorization": f"Bearer {user_response.json()['access_token']}"}

    response = await client.get("/v1/system/metrics", headers=user_headers)

    assert response.status_code == 403


async def test_system_admin_can_read_safe_config(client: AsyncClient) -> None:
    register_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "config-admin@example.com",
            "password": "correct horse battery staple",
            "display_name": "Config Admin",
        },
    )
    headers = {"Authorization": f"Bearer {register_response.json()['access_token']}"}

    response = await client.get("/v1/system/config", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "environment": "test",
        "debug": False,
        "docs_enabled": True,
        "cors_origins": ["http://localhost:3000"],
        "max_request_body_bytes": 1_048_576,
        "rate_limit_enabled": True,
        "rate_limit_backend": "memory",
        "storage_backend": "s3",
        "attachment_verification": False,
        "presence_backend": "memory",
        "typing_backend": "memory",
        "redis_fanout_enabled": False,
        "redis_signals_enabled": False,
        "webtransport_enabled": False,
        "webtransport_url": None,
        "webtransport_health_url": None,
    }
    assert "jwt_secret_key" not in body
    assert "gateway_internal_token" not in body
    assert "database_url" not in body
    assert "redis_url" not in body
    assert "s3_secret_access_key" not in body


async def test_system_config_rejects_non_admin_user(client: AsyncClient) -> None:
    await client.post(
        "/v1/auth/register",
        json={
            "email": "config-owner@example.com",
            "password": "correct horse battery staple",
            "display_name": "Config Owner",
        },
    )
    user_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "config-user@example.com",
            "password": "correct horse battery staple",
            "display_name": "Config User",
        },
    )
    headers = {"Authorization": f"Bearer {user_response.json()['access_token']}"}

    response = await client.get("/v1/system/config", headers=headers)

    assert response.status_code == 403


async def test_system_admin_can_list_and_promote_users(client: AsyncClient) -> None:
    admin_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "list-admin@example.com",
            "password": "correct horse battery staple",
            "display_name": "List Admin",
        },
    )
    user_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "list-user@example.com",
            "password": "correct horse battery staple",
            "display_name": "List User",
        },
    )
    admin_headers = {"Authorization": f"Bearer {admin_response.json()['access_token']}"}
    user_id = user_response.json()["user"]["id"]

    list_response = await client.get("/v1/system/users", headers=admin_headers)
    promote_response = await client.patch(
        f"/v1/system/users/{user_id}",
        headers=admin_headers,
        json={"is_system_admin": True},
    )
    list_after_promote_response = await client.get("/v1/system/users", headers=admin_headers)
    audit_response = await client.get("/v1/system/audit-logs", headers=admin_headers)

    assert list_response.status_code == 200
    assert [user["email"] for user in list_response.json()] == [
        "list-admin@example.com",
        "list-user@example.com",
    ]
    assert promote_response.status_code == 200
    assert promote_response.json()["is_system_admin"] is True
    assert [user["is_system_admin"] for user in list_after_promote_response.json()] == [
        True,
        True,
    ]
    assert audit_response.status_code == 200
    assert audit_response.json()[0]["action"] == "system.user_updated"
    assert audit_response.json()[0]["target_id"] == user_id
    assert audit_response.json()[0]["details"]["changes"]["is_system_admin"] == {
        "before": False,
        "after": True,
    }


async def test_system_user_management_rejects_non_admin_user(client: AsyncClient) -> None:
    await client.post(
        "/v1/auth/register",
        json={
            "email": "manage-admin@example.com",
            "password": "correct horse battery staple",
            "display_name": "Manage Admin",
        },
    )
    user_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "manage-user@example.com",
            "password": "correct horse battery staple",
            "display_name": "Manage User",
        },
    )
    user_headers = {"Authorization": f"Bearer {user_response.json()['access_token']}"}

    response = await client.get("/v1/system/users", headers=user_headers)

    assert response.status_code == 403


async def test_system_user_management_protects_last_active_admin(client: AsyncClient) -> None:
    admin_response = await client.post(
        "/v1/auth/register",
        json={
            "email": "last-admin@example.com",
            "password": "correct horse battery staple",
            "display_name": "Last Admin",
        },
    )
    admin_body = admin_response.json()
    admin_headers = {"Authorization": f"Bearer {admin_body['access_token']}"}
    admin_id = admin_body["user"]["id"]

    demote_response = await client.patch(
        f"/v1/system/users/{admin_id}",
        headers=admin_headers,
        json={"is_system_admin": False},
    )
    deactivate_response = await client.patch(
        f"/v1/system/users/{admin_id}",
        headers=admin_headers,
        json={"is_active": False},
    )

    assert demote_response.status_code == 409
    assert deactivate_response.status_code == 409
