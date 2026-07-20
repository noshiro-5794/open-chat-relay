import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import redis.asyncio as redis

from app.core.config import Settings

PRESENCE_STATUS_PRIORITY = {
    "online": 1,
    "away": 2,
    "busy": 3,
}


@dataclass(frozen=True)
class PresenceMember:
    user_id: UUID
    status: str


class PresenceStore(Protocol):
    async def mark_online(
        self, *, room_id: UUID, user_id: UUID, status: str = "online"
    ) -> None: ...

    async def mark_status(self, *, room_id: UUID, user_id: UUID, status: str) -> None: ...

    async def mark_offline(self, *, room_id: UUID, user_id: UUID) -> None: ...

    async def list_room(self, *, room_id: UUID) -> list[PresenceMember]: ...

    async def close(self) -> None: ...


class InMemoryPresenceStore:
    def __init__(self) -> None:
        self._statuses: dict[UUID, dict[UUID, str]] = defaultdict(dict)

    async def mark_online(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        status: str = "online",
    ) -> None:
        self._statuses[room_id][user_id] = status

    async def mark_status(self, *, room_id: UUID, user_id: UUID, status: str) -> None:
        self._statuses[room_id][user_id] = status

    async def mark_offline(self, *, room_id: UUID, user_id: UUID) -> None:
        room_statuses = self._statuses.get(room_id)
        if room_statuses is None:
            return
        room_statuses.pop(user_id, None)
        if not room_statuses:
            self._statuses.pop(room_id, None)

    async def list_room(self, *, room_id: UUID) -> list[PresenceMember]:
        room_statuses = self._statuses.get(room_id, {})
        return [
            PresenceMember(user_id=user_id, status=status)
            for user_id, status in sorted(room_statuses.items())
        ]

    async def close(self) -> None:
        return None


class RedisPresenceStore:
    def __init__(
        self,
        settings: Settings,
        *,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client or redis.from_url(settings.redis_url, decode_responses=True)
        self._owns_redis_client = redis_client is None

    async def mark_online(
        self,
        *,
        room_id: UUID,
        user_id: UUID,
        status: str = "online",
    ) -> None:
        member = self._member(user_id)
        expires_at = int(time.time()) + self._settings.presence_ttl_seconds
        members_key = self._members_key(room_id)
        statuses_key = self._statuses_key(room_id)

        await self._redis.zadd(members_key, {member: expires_at})
        await self._redis.hset(statuses_key, member, status)
        await self._redis.expire(members_key, self._settings.presence_ttl_seconds + 60)
        await self._redis.expire(statuses_key, self._settings.presence_ttl_seconds + 60)

    async def mark_status(self, *, room_id: UUID, user_id: UUID, status: str) -> None:
        await self.mark_online(room_id=room_id, user_id=user_id, status=status)

    async def mark_offline(self, *, room_id: UUID, user_id: UUID) -> None:
        member = self._member(user_id)
        await self._redis.zrem(self._members_key(room_id), member)
        await self._redis.hdel(self._statuses_key(room_id), member)

    async def list_room(self, *, room_id: UUID) -> list[PresenceMember]:
        members_key = self._members_key(room_id)
        statuses_key = self._statuses_key(room_id)
        now = int(time.time())
        expired_members = list(await self._redis.zrangebyscore(members_key, 0, now))
        if expired_members:
            await self._redis.zrem(members_key, *expired_members)
            await self._redis.hdel(statuses_key, *expired_members)

        members = list(await self._redis.zrange(members_key, 0, -1))
        if not members:
            return []

        statuses = await self._redis.hmget(statuses_key, members)
        users: dict[UUID, str] = {}
        for member, status in zip(members, statuses, strict=True):
            user_id = self._user_id_from_member(member)
            if user_id is None:
                continue
            normalized_status = status if isinstance(status, str) else "online"
            previous = users.get(user_id)
            if previous is None or status_priority(normalized_status) > status_priority(previous):
                users[user_id] = normalized_status

        return [
            PresenceMember(user_id=user_id, status=status)
            for user_id, status in sorted(users.items())
        ]

    async def close(self) -> None:
        if self._owns_redis_client:
            await self._redis.aclose()

    def _members_key(self, room_id: UUID) -> str:
        return f"{self._settings.presence_redis_key_prefix}:rooms:{room_id}:members"

    def _statuses_key(self, room_id: UUID) -> str:
        return f"{self._settings.presence_redis_key_prefix}:rooms:{room_id}:statuses"

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


def status_priority(status: str) -> int:
    return PRESENCE_STATUS_PRIORITY.get(status, 0)


def create_presence_store(settings: Settings) -> PresenceStore:
    if settings.effective_presence_backend() == "redis":
        return RedisPresenceStore(settings)
    return InMemoryPresenceStore()
