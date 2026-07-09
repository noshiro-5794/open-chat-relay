import argparse
import asyncio
import logging

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.services.outbox import publish_pending_outbox_batch

logger = logging.getLogger(__name__)


class RedisOutboxPublisher:
    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    async def publish(self, channel: str, message: str) -> None:
        await self._redis.publish(channel, message)


async def run_once(settings: Settings) -> int:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with session_factory() as session:
            result = await publish_pending_outbox_batch(
                session,
                publisher=RedisOutboxPublisher(redis_client),
                channel_prefix=settings.outbox_redis_channel_prefix,
                limit=settings.outbox_publisher_batch_size,
                max_attempts=settings.outbox_publisher_max_attempts,
            )
            log = logger.info if result.published or result.failed else logger.debug
            log(
                "Published outbox batch.",
                extra={"published": result.published, "failed": result.failed},
            )
            return result.published
    finally:
        await redis_client.aclose()
        await engine.dispose()


async def run_forever(settings: Settings) -> None:
    while True:
        if settings.outbox_publisher_enabled:
            await run_once(settings)
        await asyncio.sleep(settings.outbox_publisher_poll_interval_seconds)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish pending OpenChatRelay event outbox rows.")
    parser.add_argument("--once", action="store_true", help="Publish one batch and exit.")
    return parser.parse_args()


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = parse_args()
    if args.once:
        asyncio.run(run_once(settings))
        return
    asyncio.run(run_forever(settings))


if __name__ == "__main__":
    main()
