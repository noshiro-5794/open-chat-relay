import json
import logging
from typing import Protocol
from uuid import UUID, uuid4

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import Settings

logger = logging.getLogger(__name__)


class RealtimeSignalBus(Protocol):
    async def publish_room(self, *, room_id: UUID, payload: dict) -> None: ...

    async def publish_user(self, *, user_id: UUID, payload: dict) -> None: ...

    async def close(self) -> None: ...


class NoopRealtimeSignalBus:
    async def publish_room(self, *, room_id: UUID, payload: dict) -> None:
        return None

    async def publish_user(self, *, user_id: UUID, payload: dict) -> None:
        return None

    async def close(self) -> None:
        return None


class RedisRealtimeSignalBus:
    def __init__(
        self,
        settings: Settings,
        *,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client or redis.from_url(settings.redis_url, decode_responses=True)
        self._owns_redis_client = redis_client is None

    async def publish_room(self, *, room_id: UUID, payload: dict) -> None:
        await self._publish(
            f"{self._settings.outbox_redis_channel_prefix}:rooms:{room_id}:events",
            payload,
        )

    async def publish_user(self, *, user_id: UUID, payload: dict) -> None:
        await self._publish(
            f"{self._settings.outbox_redis_channel_prefix}:users:{user_id}:events",
            payload,
        )

    async def _publish(self, channel: str, payload: dict) -> None:
        signal_payload = dict(payload)
        signal_payload["origin_node_id"] = self._settings.node_id
        signal_payload["signal_id"] = uuid4().hex
        try:
            await self._redis.publish(
                channel,
                json.dumps(signal_payload, separators=(",", ":"), default=str),
            )
        except (OSError, RedisError):
            logger.warning("Redis realtime signal publish failed.", exc_info=True)

    async def close(self) -> None:
        if self._owns_redis_client:
            await self._redis.aclose()


def create_realtime_signal_bus(settings: Settings) -> RealtimeSignalBus:
    if settings.effective_realtime_redis_signals_enabled():
        return RedisRealtimeSignalBus(settings)
    return NoopRealtimeSignalBus()
