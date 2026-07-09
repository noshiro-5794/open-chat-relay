from uuid import uuid4

from app.core.config import Settings
from app.core.rate_limit import RedisFixedWindowRateLimiter
from app.main import create_app
from starlette.requests import Request
from starlette.testclient import TestClient


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds


def request_for_path(path: str, *, client_host: str = "127.0.0.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "client": (client_host, 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_general_rate_limit_returns_429() -> None:
    app = create_app(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            rate_limit_general_requests=1,
        )
    )

    with TestClient(app) as client:
        first_response = client.get("/health")
        second_response = client.get("/health")

    assert first_response.status_code == 200
    assert first_response.headers["X-RateLimit-Category"] == "general"
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"]
    assert second_response.json()["category"] == "general"


def test_webhook_rate_limit_uses_webhook_bucket() -> None:
    app = create_app(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            rate_limit_general_requests=100,
            rate_limit_webhook_requests=1,
        )
    )

    with TestClient(app) as client:
        webhook_id = uuid4()
        first_response = client.post(
            f"/v1/webhooks/incoming/{webhook_id}",
            json={"content": "hello"},
        )
        second_response = client.post(
            f"/v1/webhooks/incoming/{webhook_id}",
            json={"content": "hello"},
        )

    assert first_response.status_code == 401
    assert first_response.headers["X-RateLimit-Category"] == "webhook"
    assert second_response.status_code == 429
    assert second_response.json()["category"] == "webhook"


def test_rate_limit_can_be_disabled() -> None:
    app = create_app(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            rate_limit_enabled=False,
            rate_limit_general_requests=1,
        )
    )

    with TestClient(app) as client:
        first_response = client.get("/health")
        second_response = client.get("/health")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert "X-RateLimit-Category" not in second_response.headers


async def test_redis_rate_limiter_uses_shared_fixed_window_bucket() -> None:
    redis_client = FakeRedis()
    limiter = RedisFixedWindowRateLimiter(
        Settings(
            environment="local",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            rate_limit_general_requests=1,
            rate_limit_window_seconds=60,
        ),
        redis_client=redis_client,
    )
    request = request_for_path("/health", client_host="10.0.0.10")

    first_decision = await limiter.check(request)
    second_decision = await limiter.check(request)

    assert first_decision.allowed is True
    assert first_decision.remaining == 0
    assert second_decision.allowed is False
    assert second_decision.retry_after_seconds == 60
    assert redis_client.counts["open_chat_relay:rate_limit:general:10.0.0.10"] == 2
