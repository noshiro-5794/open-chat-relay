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


async def create_room(client: AsyncClient, headers: dict[str, str]) -> dict:
    workspace_response = await client.post(
        "/v1/workspaces",
        json={"name": "Message Team"},
        headers=headers,
    )
    workspace_id = workspace_response.json()["id"]
    room_response = await client.post(
        f"/v1/workspaces/{workspace_id}/rooms",
        json={"name": "General"},
        headers=headers,
    )
    return room_response.json()


async def test_send_message_creates_durable_event(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)

    response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "hello"},
        headers=headers,
    )

    assert response.status_code == 201
    message = response.json()
    assert message["content"] == "hello"
    assert message["message_type"] == "text"
    assert message["sender_type"] == "user"
    assert message["sender_id"] is not None
    assert message["sender_bot_id"] is None

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    assert events_response.status_code == 200
    events = events_response.json()
    assert len(events) == 1
    assert events[0]["type"] == "message.created"
    assert events[0]["actor_type"] == "user"
    assert events[0]["actor_id"] == message["sender_id"]
    assert events[0]["actor_bot_id"] is None
    assert events[0]["room_event_seq"] == 1
    assert events[0]["workspace_event_seq"] == 1
    assert events[0]["data"]["message_id"] == message["id"]
    assert events[0]["data"]["sender_type"] == "user"


async def test_message_history_is_ordered_oldest_to_newest(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)

    await client.post(f"/v1/rooms/{room['id']}/messages", json={"content": "one"}, headers=headers)
    await client.post(f"/v1/rooms/{room['id']}/messages", json={"content": "two"}, headers=headers)

    response = await client.get(f"/v1/rooms/{room['id']}/messages", headers=headers)

    assert response.status_code == 200
    messages = response.json()
    assert [message["content"] for message in messages] == ["one", "two"]


async def test_message_history_page_uses_before_cursor(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    created_messages = []
    for content in ["one", "two", "three", "four", "five"]:
        response = await client.post(
            f"/v1/rooms/{room['id']}/messages",
            json={"content": content},
            headers=headers,
        )
        created_messages.append(response.json())

    first_page_response = await client.get(
        f"/v1/rooms/{room['id']}/messages/page?limit=2",
        headers=headers,
    )
    first_page = first_page_response.json()

    assert first_page_response.status_code == 200
    assert [message["content"] for message in first_page["items"]] == ["four", "five"]
    assert first_page["next_before_message_id"] == created_messages[3]["id"]
    assert first_page["has_more"] is True

    second_page_response = await client.get(
        (
            f"/v1/rooms/{room['id']}/messages/page?limit=2"
            f"&before_message_id={first_page['next_before_message_id']}"
        ),
        headers=headers,
    )
    second_page = second_page_response.json()

    assert second_page_response.status_code == 200
    assert [message["content"] for message in second_page["items"]] == ["two", "three"]
    assert second_page["next_before_message_id"] == created_messages[1]["id"]
    assert second_page["has_more"] is True

    third_page_response = await client.get(
        (
            f"/v1/rooms/{room['id']}/messages/page?limit=2"
            f"&before_message_id={second_page['next_before_message_id']}"
        ),
        headers=headers,
    )
    third_page = third_page_response.json()

    assert third_page_response.status_code == 200
    assert [message["content"] for message in third_page["items"]] == ["one"]
    assert third_page["next_before_message_id"] is None
    assert third_page["has_more"] is False


async def test_message_history_page_rejects_unknown_cursor(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)

    response = await client.get(
        f"/v1/rooms/{room['id']}/messages/page?before_message_id={room['id']}",
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Message cursor not found."


async def test_search_messages_matches_content_case_insensitively(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "Deploy succeeded"},
        headers=headers,
    )
    await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "plain chat"},
        headers=headers,
    )
    latest_match_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "Another DEPLOY event"},
        headers=headers,
    )

    response = await client.get(
        f"/v1/rooms/{room['id']}/messages/search?q=deploy",
        headers=headers,
    )

    assert response.status_code == 200
    results = response.json()
    assert [message["content"] for message in results] == [
        "Another DEPLOY event",
        "Deploy succeeded",
    ]
    assert results[0]["id"] == latest_match_response.json()["id"]


async def test_search_messages_excludes_deleted_messages(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    create_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "secret searchable text"},
        headers=headers,
    )
    await client.delete(
        f"/v1/rooms/{room['id']}/messages/{create_response.json()['id']}",
        headers=headers,
    )

    response = await client.get(
        f"/v1/rooms/{room['id']}/messages/search?q=searchable",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_create_reply_and_list_thread_replies(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    parent_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "parent"},
        headers=headers,
    )
    parent = parent_response.json()

    reply_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "reply", "reply_to_id": parent["id"]},
        headers=headers,
    )
    replies_response = await client.get(
        f"/v1/rooms/{room['id']}/messages/{parent['id']}/replies",
        headers=headers,
    )

    assert reply_response.status_code == 201
    reply = reply_response.json()
    assert reply["content"] == "reply"
    assert reply["reply_to_id"] == parent["id"]

    assert replies_response.status_code == 200
    replies = replies_response.json()
    assert [message["id"] for message in replies] == [reply["id"]]
    assert replies[0]["reply_to_id"] == parent["id"]

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    events = events_response.json()
    assert events[1]["type"] == "message.created"
    assert events[1]["data"]["reply_to_id"] == parent["id"]


async def test_reply_target_must_exist_in_room(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    other_room_response = await client.post(
        f"/v1/workspaces/{room['workspace_id']}/rooms",
        json={"name": "Other"},
        headers=headers,
    )
    other_room = other_room_response.json()
    other_message_response = await client.post(
        f"/v1/rooms/{other_room['id']}/messages",
        json={"content": "other"},
        headers=headers,
    )

    response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "bad reply", "reply_to_id": other_message_response.json()["id"]},
        headers=headers,
    )

    assert response.status_code == 404


async def test_room_events_support_after_seq(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)

    await client.post(f"/v1/rooms/{room['id']}/messages", json={"content": "one"}, headers=headers)
    await client.post(f"/v1/rooms/{room['id']}/messages", json={"content": "two"}, headers=headers)

    response = await client.get(f"/v1/rooms/{room['id']}/events?after_seq=1", headers=headers)

    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["room_event_seq"] == 2
    assert events[0]["data"]["content"] == "two"


async def test_update_message_creates_durable_event(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    create_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "before"},
        headers=headers,
    )
    message_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/v1/rooms/{room['id']}/messages/{message_id}",
        json={"content": "after"},
        headers=headers,
    )

    assert update_response.status_code == 200
    assert update_response.json()["content"] == "after"

    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)
    events = events_response.json()
    assert [event["type"] for event in events] == ["message.created", "message.updated"]
    assert events[1]["room_event_seq"] == 2
    assert events[1]["data"]["content"] == "after"


async def test_delete_message_creates_event_and_hides_from_history(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    create_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "delete me"},
        headers=headers,
    )
    message_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/v1/rooms/{room['id']}/messages/{message_id}",
        headers=headers,
    )
    history_response = await client.get(f"/v1/rooms/{room['id']}/messages", headers=headers)
    events_response = await client.get(f"/v1/rooms/{room['id']}/events", headers=headers)

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_at"] is not None
    assert history_response.status_code == 200
    assert history_response.json() == []
    events = events_response.json()
    assert [event["type"] for event in events] == ["message.created", "message.deleted"]
    assert events[1]["room_event_seq"] == 2


async def test_message_delete_command_matches_delete_endpoint(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)
    create_response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "delete over post"},
        headers=headers,
    )
    message_id = create_response.json()["id"]

    delete_response = await client.post(
        f"/v1/rooms/{room['id']}/messages/{message_id}/commands",
        json={"type": "message.delete"},
        headers=headers,
    )
    history_response = await client.get(f"/v1/rooms/{room['id']}/messages", headers=headers)

    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_at"] is not None
    assert history_response.status_code == 200
    assert history_response.json() == []


async def test_user_must_join_room_before_sending_messages(client: AsyncClient) -> None:
    headers = await auth_headers(client)
    room = await create_room(client, headers)

    leave_response = await client.post(f"/v1/rooms/{room['id']}/leave", headers=headers)
    assert leave_response.status_code == 200

    response = await client.post(
        f"/v1/rooms/{room['id']}/messages",
        json={"content": "hello"},
        headers=headers,
    )

    assert response.status_code == 403
