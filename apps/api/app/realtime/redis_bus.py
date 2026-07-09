import asyncio
import json
import logging
from typing import Any
from uuid import UUID

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.realtime.manager import RealtimeConnectionManager, manager

logger = logging.getLogger(__name__)


async def redis_realtime_fanout_loop(
    settings: Settings,
    *,
    connection_manager: RealtimeConnectionManager = manager,
) -> None:
    room_pattern = f"{settings.outbox_redis_channel_prefix}:rooms:*:events"
    user_pattern = f"{settings.outbox_redis_channel_prefix}:users:*:events"

    while True:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        try:
            async with redis_client.pubsub() as pubsub:
                await pubsub.psubscribe(room_pattern, user_pattern)
                logger.info(
                    "Redis realtime fanout subscriber started.",
                    extra={"patterns": [room_pattern, user_pattern]},
                )
                async for message in pubsub.listen():
                    await handle_pubsub_message(
                        message,
                        channel_prefix=settings.outbox_redis_channel_prefix,
                        local_node_id=settings.node_id,
                        connection_manager=connection_manager,
                    )
        except asyncio.CancelledError:
            raise
        except (OSError, RedisError):
            logger.warning("Redis realtime fanout subscriber disconnected.", exc_info=True)
        finally:
            await redis_client.aclose()

        await asyncio.sleep(settings.realtime_redis_reconnect_seconds)


async def handle_pubsub_message(
    message: dict[str, Any],
    *,
    channel_prefix: str,
    local_node_id: str | None = None,
    connection_manager: RealtimeConnectionManager = manager,
) -> bool:
    if message.get("type") != "pmessage":
        return False

    channel = message.get("channel")
    room_id = room_id_from_channel(channel, channel_prefix=channel_prefix)
    user_id = user_id_from_channel(channel, channel_prefix=channel_prefix)
    if room_id is None and user_id is None:
        return False

    payload = decode_payload(message.get("data"))
    if payload is None:
        logger.warning("Ignored invalid realtime fanout payload.", extra={"channel": channel})
        return False

    origin_node_id = payload.pop("origin_node_id", None)
    payload.pop("signal_id", None)
    if local_node_id is not None and origin_node_id == local_node_id:
        return False

    event_id = payload.get("event_id")
    if isinstance(event_id, str) and connection_manager.has_seen_event(event_id):
        return False

    if room_id is not None:
        await connection_manager.broadcast_room(room_id, payload)
    elif user_id is not None:
        await connection_manager.send_user(user_id, payload)
    return True


def room_id_from_channel(channel: object, *, channel_prefix: str) -> UUID | None:
    return id_from_channel(channel, channel_prefix=channel_prefix, entity="rooms")


def user_id_from_channel(channel: object, *, channel_prefix: str) -> UUID | None:
    return id_from_channel(channel, channel_prefix=channel_prefix, entity="users")


def id_from_channel(channel: object, *, channel_prefix: str, entity: str) -> UUID | None:
    if not isinstance(channel, str):
        return None

    prefix = f"{channel_prefix}:{entity}:"
    suffix = ":events"
    if not channel.startswith(prefix) or not channel.endswith(suffix):
        return None

    raw_id = channel.removeprefix(prefix).removesuffix(suffix)
    try:
        return UUID(raw_id)
    except ValueError:
        return None


def decode_payload(data: object) -> dict[str, Any] | None:
    if not isinstance(data, str):
        return None

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None
    return payload
