from app.core.config import Settings
from app.storage.service import StorageService, UploadedObjectMetadata
from httpx import AsyncClient


async def auth_headers(client: AsyncClient, email: str = "file@example.com") -> dict[str, str]:
    response = await client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "password": "correct horse battery staple",
            "display_name": "File User",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def create_room(client: AsyncClient, headers: dict[str, str]) -> dict:
    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Files Team"},
        headers=headers,
    )
    workspace_id = workspace_response.json()["id"]
    room_response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "General"},
        headers=headers,
    )
    return room_response.json()


async def create_attachment(client: AsyncClient, headers: dict[str, str], room_id: str) -> dict:
    response = await client.post(
        f"/v1/rooms/{room_id}/attachments",
        json={
            "filename": "report.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1234,
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["attachment"]


async def confirm_attachment(
    client: AsyncClient,
    headers: dict[str, str],
    room_id: str,
    attachment_id: str,
) -> dict:
    response = await client.post(
        f"/v1/rooms/{room_id}/attachments/{attachment_id}/confirm",
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


async def test_create_attachment_intent(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)

    response = await client.post(
        f"/v1/rooms/{room['id']}/attachments",
        json={
            "filename": "report.pdf",
            "content_type": "application/pdf",
            "size_bytes": 1234,
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["upload_url"].startswith("http://localhost:9000/open-chat-relay/")
    assert "X-Amz-Signature=" in body["upload_url"]
    assert body["attachment"]["status"] == "pending_upload"
    assert body["attachment"]["storage_key"].endswith("-report.pdf")


async def test_create_message_with_attachment(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    attachment = await create_attachment(client, headers, room["id"])
    uploaded_attachment = await confirm_attachment(client, headers, room["id"], attachment["id"])
    assert uploaded_attachment["status"] == "uploaded"

    response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "", "attachment_ids": [attachment["id"]]},
        headers=headers,
    )

    assert response.status_code == 201
    message = response.json()
    assert message["content"] == ""
    assert message["attachments"][0]["id"] == attachment["id"]
    assert message["attachments"][0]["status"] == "attached"

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    event = events_response.json()[0]
    assert event["data"]["attachments"][0]["id"] == attachment["id"]


async def test_uploaded_attachment_can_create_download_intent(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    attachment = await create_attachment(client, headers, room["id"])
    uploaded_attachment = await confirm_attachment(client, headers, room["id"], attachment["id"])

    response = await client.get(
        f"/v1/rooms/{room['id']}/attachments/{attachment['id']}/download",
        headers=headers,
    )

    assert uploaded_attachment["status"] == "uploaded"
    assert response.status_code == 200
    body = response.json()
    assert body["attachment"]["id"] == attachment["id"]
    assert body["expires_in_seconds"] == 900
    assert body["download_url"].startswith("http://localhost:9000/open-chat-relay/")
    assert "X-Amz-Signature=" in body["download_url"]


async def test_pending_attachment_cannot_create_download_intent(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    attachment = await create_attachment(client, headers, room["id"])

    response = await client.get(
        f"/v1/rooms/{room['id']}/attachments/{attachment['id']}/download",
        headers=headers,
    )

    assert response.status_code == 404


async def test_attachment_cannot_be_reused(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    attachment = await create_attachment(client, headers, room["id"])
    await confirm_attachment(client, headers, room["id"], attachment["id"])

    first_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "first", "attachment_ids": [attachment["id"]]},
        headers=headers,
    )
    second_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "second", "attachment_ids": [attachment["id"]]},
        headers=headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 404


async def test_pending_attachment_cannot_be_bound_to_message(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    attachment = await create_attachment(client, headers, room["id"])

    response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "not yet", "attachment_ids": [attachment["id"]]},
        headers=headers,
    )

    assert response.status_code == 404


async def test_attached_attachment_cannot_be_confirmed_again(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    attachment = await create_attachment(client, headers, room["id"])
    await confirm_attachment(client, headers, room["id"], attachment["id"])

    message_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "attached", "attachment_ids": [attachment["id"]]},
        headers=headers,
    )
    confirm_response = await client.post(
        f"/v1/rooms/{room['id']}/attachments/{attachment['id']}/confirm",
        headers=headers,
    )

    assert message_response.status_code == 201
    assert confirm_response.status_code == 409


async def test_confirm_attachment_verifies_uploaded_object(
    client: AsyncClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(Settings, "effective_verify_attachment_uploads", lambda _settings: True)
    monkeypatch.setattr(
        StorageService,
        "head_object",
        lambda _service, *, storage_key: UploadedObjectMetadata(
            size_bytes=1234,
            content_type="application/pdf",
        ),
    )
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    attachment = await create_attachment(client, headers, room["id"])

    response = await client.post(
        f"/v1/rooms/{room['id']}/attachments/{attachment['id']}/confirm",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "uploaded"


async def test_confirm_attachment_rejects_missing_uploaded_object(
    client: AsyncClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(Settings, "effective_verify_attachment_uploads", lambda _settings: True)
    monkeypatch.setattr(StorageService, "head_object", lambda _service, *, storage_key: None)
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    attachment = await create_attachment(client, headers, room["id"])

    response = await client.post(
        f"/v1/rooms/{room['id']}/attachments/{attachment['id']}/confirm",
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Attachment object has not been uploaded."


async def test_confirm_attachment_rejects_uploaded_object_metadata_mismatch(
    client: AsyncClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(Settings, "effective_verify_attachment_uploads", lambda _settings: True)
    monkeypatch.setattr(
        StorageService,
        "head_object",
        lambda _service, *, storage_key: UploadedObjectMetadata(
            size_bytes=9999,
            content_type="application/pdf",
        ),
    )
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    attachment = await create_attachment(client, headers, room["id"])

    response = await client.post(
        f"/v1/rooms/{room['id']}/attachments/{attachment['id']}/confirm",
        headers=headers,
    )

    assert response.status_code == 422
    assert (
        response.json()["detail"] == "Attachment object metadata does not match the upload intent."
    )
