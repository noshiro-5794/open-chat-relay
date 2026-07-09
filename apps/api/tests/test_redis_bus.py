import json
from uuid import UUID, uuid4

from app.realtime.redis_bus import handle_pubsub_message, room_id_from_channel, user_id_from_channel


class FakeConnectionManager:
    def __init__(self) -> None:
        self.seen_event_ids: set[str] = set()
        self.broadcasts: list[tuple[UUID, dict]] = []
        self.user_messages: list[tuple[UUID, dict]] = []

    def has_seen_event(self, event_id: str) -> bool:
        return event_id in self.seen_event_ids

    async def broadcast_room(self, room_id: UUID, payload: dict) -> None:
        self.broadcasts.append((room_id, payload))
        event_id = payload.get("event_id")
        if isinstance(event_id, str):
            self.seen_event_ids.add(event_id)

    async def send_user(self, user_id: UUID, payload: dict) -> None:
        self.user_messages.append((user_id, payload))


def test_room_id_from_channel_parses_room_event_channel() -> None:
    room_id = uuid4()

    parsed = room_id_from_channel(
        f"test:rooms:{room_id}:events",
        channel_prefix="test",
    )

    assert parsed == room_id


def test_room_id_from_channel_rejects_unknown_channel() -> None:
    assert room_id_from_channel("test:workspaces:abc:events", channel_prefix="test") is None
    assert room_id_from_channel("test:rooms:not-a-uuid:events", channel_prefix="test") is None


def test_user_id_from_channel_parses_user_event_channel() -> None:
    user_id = uuid4()

    parsed = user_id_from_channel(
        f"test:users:{user_id}:events",
        channel_prefix="test",
    )

    assert parsed == user_id


async def test_handle_pubsub_message_broadcasts_room_event() -> None:
    room_id = uuid4()
    event_id = str(uuid4())
    manager = FakeConnectionManager()
    message = {
        "type": "pmessage",
        "channel": f"test:rooms:{room_id}:events",
        "data": json.dumps({"type": "message.created", "event_id": event_id}),
    }

    handled = await handle_pubsub_message(
        message,
        channel_prefix="test",
        connection_manager=manager,
    )

    assert handled is True
    assert manager.broadcasts == [
        (room_id, {"type": "message.created", "event_id": event_id}),
    ]
    assert event_id in manager.seen_event_ids


async def test_handle_pubsub_message_sends_user_event() -> None:
    user_id = uuid4()
    manager = FakeConnectionManager()
    message = {
        "type": "pmessage",
        "channel": f"test:users:{user_id}:events",
        "data": json.dumps({"type": "notification.created", "notification_id": "n1"}),
    }

    handled = await handle_pubsub_message(
        message,
        channel_prefix="test",
        connection_manager=manager,
    )

    assert handled is True
    assert manager.user_messages == [
        (user_id, {"type": "notification.created", "notification_id": "n1"}),
    ]


async def test_handle_pubsub_message_skips_seen_event() -> None:
    room_id = uuid4()
    event_id = str(uuid4())
    manager = FakeConnectionManager()
    manager.seen_event_ids.add(event_id)
    message = {
        "type": "pmessage",
        "channel": f"test:rooms:{room_id}:events",
        "data": json.dumps({"type": "message.created", "event_id": event_id}),
    }

    handled = await handle_pubsub_message(
        message,
        channel_prefix="test",
        connection_manager=manager,
    )

    assert handled is False
    assert manager.broadcasts == []


async def test_handle_pubsub_message_skips_local_ephemeral_signal() -> None:
    room_id = uuid4()
    manager = FakeConnectionManager()
    message = {
        "type": "pmessage",
        "channel": f"test:rooms:{room_id}:events",
        "data": json.dumps(
            {
                "type": "typing.updated",
                "origin_node_id": "node-a",
                "signal_id": "signal-1",
                "data": {"status": "started"},
            }
        ),
    }

    handled = await handle_pubsub_message(
        message,
        channel_prefix="test",
        local_node_id="node-a",
        connection_manager=manager,
    )

    assert handled is False
    assert manager.broadcasts == []


async def test_handle_pubsub_message_broadcasts_remote_signal_without_internal_fields() -> None:
    room_id = uuid4()
    manager = FakeConnectionManager()
    message = {
        "type": "pmessage",
        "channel": f"test:rooms:{room_id}:events",
        "data": json.dumps(
            {
                "type": "typing.updated",
                "origin_node_id": "node-b",
                "signal_id": "signal-1",
                "data": {"status": "started"},
            }
        ),
    }

    handled = await handle_pubsub_message(
        message,
        channel_prefix="test",
        local_node_id="node-a",
        connection_manager=manager,
    )

    assert handled is True
    assert manager.broadcasts == [
        (room_id, {"type": "typing.updated", "data": {"status": "started"}})
    ]


async def test_handle_pubsub_message_ignores_invalid_payload() -> None:
    room_id = uuid4()
    manager = FakeConnectionManager()

    handled = await handle_pubsub_message(
        {
            "type": "pmessage",
            "channel": f"test:rooms:{room_id}:events",
            "data": "not-json",
        },
        channel_prefix="test",
        connection_manager=manager,
    )

    assert handled is False
    assert manager.broadcasts == []
