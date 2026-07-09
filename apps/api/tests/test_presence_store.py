from uuid import uuid4

from app.core.config import Settings
from app.realtime.presence_store import RedisPresenceStore


class FakeRedis:
    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, int]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.expires: dict[str, int] = {}

    async def zadd(self, key: str, mapping: dict[str, int]) -> None:
        self.zsets.setdefault(key, {}).update(mapping)

    async def hset(self, key: str, field: str, value: str) -> None:
        self.hashes.setdefault(key, {})[field] = value

    async def expire(self, key: str, seconds: int) -> None:
        self.expires[key] = seconds

    async def zrangebyscore(self, key: str, minimum: int, maximum: int) -> list[str]:
        return [
            member
            for member, score in self.zsets.get(key, {}).items()
            if minimum <= score <= maximum
        ]

    async def zrem(self, key: str, *members: str) -> None:
        for member in members:
            self.zsets.get(key, {}).pop(member, None)

    async def hdel(self, key: str, *fields: str) -> None:
        for field in fields:
            self.hashes.get(key, {}).pop(field, None)

    async def zrange(self, key: str, start: int, end: int) -> list[str]:
        members = sorted(self.zsets.get(key, {}))
        if end == -1:
            return members[start:]
        return members[start : end + 1]

    async def hmget(self, key: str, fields: list[str]) -> list[str | None]:
        values = self.hashes.get(key, {})
        return [values.get(field) for field in fields]


def settings_for_node(node_id: str) -> Settings:
    return Settings(
        environment="local",
        node_id=node_id,
        jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
        presence_backend="redis",
        presence_ttl_seconds=120,
    )


async def test_redis_presence_store_keeps_same_user_online_across_nodes() -> None:
    redis_client = FakeRedis()
    room_id = uuid4()
    user_id = uuid4()
    first_node = RedisPresenceStore(settings_for_node("node-a"), redis_client=redis_client)
    second_node = RedisPresenceStore(settings_for_node("node-b"), redis_client=redis_client)

    await first_node.mark_online(room_id=room_id, user_id=user_id, status="online")
    await second_node.mark_online(room_id=room_id, user_id=user_id, status="busy")

    members = await first_node.list_room(room_id=room_id)
    assert [(member.user_id, member.status) for member in members] == [(user_id, "busy")]

    await second_node.mark_offline(room_id=room_id, user_id=user_id)
    members = await first_node.list_room(room_id=room_id)
    assert [(member.user_id, member.status) for member in members] == [(user_id, "online")]

    await first_node.mark_offline(room_id=room_id, user_id=user_id)
    assert await first_node.list_room(room_id=room_id) == []
