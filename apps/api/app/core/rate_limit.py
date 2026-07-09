import logging
import time
from dataclasses import dataclass
from typing import Protocol

import redis.asyncio as redis
from fastapi import Request
from redis.exceptions import RedisError

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class RateLimitDecision:
    allowed: bool
    category: str
    limit: int
    remaining: int
    retry_after_seconds: int


@dataclass
class RateLimitBucket:
    count: int
    reset_at: float


class RateLimiter(Protocol):
    async def check(self, request: Request) -> RateLimitDecision: ...

    async def close(self) -> None: ...


class InMemoryFixedWindowRateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._buckets: dict[str, RateLimitBucket] = {}

    async def check(self, request: Request) -> RateLimitDecision:
        category = request_category(request, self._settings)
        limit = category_limit(category, self._settings)
        now = time.monotonic()
        key = rate_limit_key(request, category)
        bucket = self._buckets.get(key)

        if bucket is None or bucket.reset_at <= now:
            self._cleanup(now)
            bucket = RateLimitBucket(
                count=0,
                reset_at=now + self._settings.rate_limit_window_seconds,
            )
            self._buckets[key] = bucket

        if bucket.count >= limit:
            retry_after = max(1, int(bucket.reset_at - now))
            return RateLimitDecision(
                allowed=False,
                category=category,
                limit=limit,
                remaining=0,
                retry_after_seconds=retry_after,
            )

        bucket.count += 1
        return RateLimitDecision(
            allowed=True,
            category=category,
            limit=limit,
            remaining=max(0, limit - bucket.count),
            retry_after_seconds=max(1, int(bucket.reset_at - now)),
        )

    async def close(self) -> None:
        return None

    def _cleanup(self, now: float) -> None:
        expired_keys = [key for key, bucket in self._buckets.items() if bucket.reset_at <= now]
        for key in expired_keys:
            del self._buckets[key]


class RedisFixedWindowRateLimiter:
    def __init__(
        self,
        settings: Settings,
        *,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client or redis.from_url(settings.redis_url, decode_responses=True)
        self._owns_redis_client = redis_client is None

    async def check(self, request: Request) -> RateLimitDecision:
        category = request_category(request, self._settings)
        limit = category_limit(category, self._settings)
        key = self._redis_key(rate_limit_key(request, category))

        try:
            count = int(await self._redis.incr(key))
            ttl = int(await self._redis.ttl(key))
            if count == 1 or ttl < 0:
                await self._redis.expire(key, self._settings.rate_limit_window_seconds)
                ttl = self._settings.rate_limit_window_seconds
        except (OSError, RedisError):
            logger.warning("Redis rate limiter unavailable.", exc_info=True)
            if not self._settings.rate_limit_fail_open:
                raise
            return RateLimitDecision(
                allowed=True,
                category=category,
                limit=limit,
                remaining=max(0, limit - 1),
                retry_after_seconds=self._settings.rate_limit_window_seconds,
            )

        retry_after = max(1, ttl)
        if count > limit:
            return RateLimitDecision(
                allowed=False,
                category=category,
                limit=limit,
                remaining=0,
                retry_after_seconds=retry_after,
            )

        return RateLimitDecision(
            allowed=True,
            category=category,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=retry_after,
        )

    async def close(self) -> None:
        if self._owns_redis_client:
            await self._redis.aclose()

    def _redis_key(self, key: str) -> str:
        return f"{self._settings.rate_limit_redis_key_prefix}:{key}"


def create_rate_limiter(settings: Settings) -> RateLimiter:
    if settings.effective_rate_limit_backend() == "redis":
        return RedisFixedWindowRateLimiter(settings)
    return InMemoryFixedWindowRateLimiter(settings)


def request_category(request: Request, settings: Settings) -> str:
    path = request.url.path
    api_prefix = settings.api_v1_prefix.rstrip("/")
    if path.startswith(f"{api_prefix}/auth"):
        return "auth"
    if path.startswith(f"{api_prefix}/webhooks"):
        return "webhook"
    if path.startswith(f"{api_prefix}/app"):
        return "app_api"
    return "general"


def category_limit(category: str, settings: Settings) -> int:
    if category == "auth":
        return settings.rate_limit_auth_requests
    if category == "webhook":
        return settings.rate_limit_webhook_requests
    if category == "app_api":
        return settings.rate_limit_app_api_requests
    return settings.rate_limit_general_requests


def rate_limit_key(request: Request, category: str) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_id = forwarded_for.split(",", maxsplit=1)[0].strip()
    elif request.client is not None:
        client_id = request.client.host
    else:
        client_id = "unknown"
    return f"{category}:{client_id}"
