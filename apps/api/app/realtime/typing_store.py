import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import redis.asyncio as redis

from app.core.config import Settings


@dataclass(frozen=True)
class TypingMember:
    user_id: UUID


class TypingStore(Protocol):
    async def mark_started(self, *, room_id: UUID, user_id: UUID) -> None: ...

    async def mark_stopped(self, *, room_id: UUID, user_id: UUID) -> None: ...

    async def list_room(self, *, room_id: UUID) -> list[TypingMember]: ...

    async def close(self) -> None: ...


class InMemoryTypingStore:
    def __init__(self) -> None:
        self._typing_users: dict[UUID, set[UUID]] = defaultdict(set)

    async def mark_started(self, *, room_id: UUID, user_id: UUID) -> None:
        self._typing_users[room_id].add(user_id)

    async def mark_stopped(self, *, room_id: UUID, user_id: UUID) -> None:
        room_users = self._typing_users.get(room_id)
        if room_users is None:
            return
        room_users.discard(user_id)
        if not room_users:
            self._typing_users.pop(room_id, None)

    async def list_room(self, *, room_id: UUID) -> list[TypingMember]:
        return [TypingMember(user_id=user_id) for user_id in sorted(self._typing_users[room_id])]

    async def close(self) -> None:
        return None


class RedisTypingStore:
    def __init__(
        self,
        settings: Settings,
        *,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client or redis.from_url(settings.redis_url, decode_responses=True)
        self._owns_redis_client = redis_client is None

    async def mark_started(self, *, room_id: UUID, user_id: UUID) -> None:
        key = self._key(room_id)
        member = self._member(user_id)
        expires_at = int(time.time()) + self._settings.typing_ttl_seconds
        await self._redis.zadd(key, {member: expires_at})
        await self._redis.expire(key, self._settings.typing_ttl_seconds + 30)

    async def mark_stopped(self, *, room_id: UUID, user_id: UUID) -> None:
        await self._redis.zrem(self._key(room_id), self._member(user_id))

    async def list_room(self, *, room_id: UUID) -> list[TypingMember]:
        key = self._key(room_id)
        now = int(time.time())
        await self._redis.zremrangebyscore(key, 0, now)
        members = list(await self._redis.zrange(key, 0, -1))
        user_ids: set[UUID] = set()
        for member in members:
            user_id = self._user_id_from_member(member)
            if user_id is not None:
                user_ids.add(user_id)
        return [TypingMember(user_id=user_id) for user_id in sorted(user_ids)]

    async def close(self) -> None:
        if self._owns_redis_client:
            await self._redis.aclose()

    def _key(self, room_id: UUID) -> str:
        return f"{self._settings.typing_redis_key_prefix}:rooms:{room_id}:users"

    def _member(self, user_id: UUID) -> str:
        return f"{self._settings.node_id}:{user_id}"

    def _user_id_from_member(self, member: str) -> UUID | None:
        _, _, raw_user_id = member.partition(":")
        if not raw_user_id:
            return None
        try:
            return UUID(raw_user_id)
        except ValueError:
            return None


def create_typing_store(settings: Settings) -> TypingStore:
    if settings.effective_typing_backend() == "redis":
        return RedisTypingStore(settings)
    return InMemoryTypingStore()
