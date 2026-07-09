from uuid import uuid4

from app.core.config import Settings
from app.realtime.typing_store import RedisTypingStore


class FakeRedis:
    def __init__(self) -> None:
        self.zsets: dict[str, dict[str, int]] = {}
        self.expires: dict[str, int] = {}

    async def zadd(self, key: str, mapping: dict[str, int]) -> None:
        self.zsets.setdefault(key, {}).update(mapping)

    async def expire(self, key: str, seconds: int) -> None:
        self.expires[key] = seconds

    async def zrem(self, key: str, *members: str) -> None:
        for member in members:
            self.zsets.get(key, {}).pop(member, None)

    async def zremrangebyscore(self, key: str, minimum: int, maximum: int) -> None:
        expired_members = [
            member
            for member, score in self.zsets.get(key, {}).items()
            if minimum <= score <= maximum
        ]
        for member in expired_members:
            self.zsets.get(key, {}).pop(member, None)

    async def zrange(self, key: str, start: int, end: int) -> list[str]:
        members = sorted(self.zsets.get(key, {}))
        if end == -1:
            return members[start:]
        return members[start : end + 1]


def settings_for_node(node_id: str) -> Settings:
    return Settings(
        environment="local",
        node_id=node_id,
        jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
        typing_backend="redis",
        typing_ttl_seconds=10,
    )


async def test_redis_typing_store_keeps_same_user_typing_across_nodes() -> None:
    redis_client = FakeRedis()
    room_id = uuid4()
    user_id = uuid4()
    first_node = RedisTypingStore(settings_for_node("node-a"), redis_client=redis_client)
    second_node = RedisTypingStore(settings_for_node("node-b"), redis_client=redis_client)

    await first_node.mark_started(room_id=room_id, user_id=user_id)
    await second_node.mark_started(room_id=room_id, user_id=user_id)

    members = await first_node.list_room(room_id=room_id)
    assert [member.user_id for member in members] == [user_id]

    await second_node.mark_stopped(room_id=room_id, user_id=user_id)
    members = await first_node.list_room(room_id=room_id)
    assert [member.user_id for member in members] == [user_id]

    await first_node.mark_stopped(room_id=room_id, user_id=user_id)
    assert await first_node.list_room(room_id=room_id) == []
