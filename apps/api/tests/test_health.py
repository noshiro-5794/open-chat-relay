from app.api.v1.routes import capabilities as capabilities_route
from app.core.config import Settings
from httpx import AsyncClient


async def test_health_endpoint(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_ready_endpoint_checks_dependencies(client: AsyncClient) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {
        "database": "ok",
        "redis": "skipped",
    }


async def test_capabilities_endpoint(client: AsyncClient) -> None:
    response = await client.get("/v1/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["features"]["durable_events"] is True
    assert body["features"]["ephemeral_signals"] is True
    assert body["features"]["session_resume"] is True
    assert body["features"]["incoming_webhooks"] is True
    assert body["features"]["read_states"] is True
    assert body["features"]["membership_management"] is True
    assert body["features"]["message_replies"] is True
    assert body["features"]["message_search"] is True
    assert body["features"]["audit_logs"] is True
    assert body["features"]["attachment_verification"] is False
    assert body["features"]["event_outbox"] is True
    assert body["features"]["datagrams"] is False
    assert body["transport_negotiation"]["preferred_order"] == [
        "webtransport",
        "websocket",
        "sse",
    ]
    assert body["transport_negotiation"]["fallback_policy"] == "first_available"
    assert body["protocol"]["version"] == "ocr.realtime.v1"
    assert "message.send" in body["protocol"]["realtime_commands"]
    assert "typing.update" in body["protocol"]["realtime_commands"]
    assert "room.read_state_updated" in body["protocol"]["event_types"]
    assert "typing.updated" in body["protocol"]["event_types"]
    assert body["realtime_frame"] == {
        "version": "ocr.realtime.frame.v1",
        "encoding": "jsonl",
        "content_type": "application/x-ndjson",
        "delimiter": "\n",
        "max_frame_bytes": 1_048_576,
    }
    assert body["transports"]["websocket"]["available"] is True
    assert body["transports"]["websocket"]["status"] == "available"
    assert body["transports"]["webtransport"]["available"] is False
    assert body["transports"]["webtransport"]["status"] == "disabled"
    assert body["transports"]["webtransport"]["fallback_to"] == "websocket"
    assert body["transports"]["websocket"]["fallback_to"] == "sse"
    assert body["transports"]["sse"]["mode"] == "server_stream"


async def test_webtransport_status_uses_gateway_probe(monkeypatch) -> None:
    class HealthyResponse:
        status = 200

        def __enter__(self) -> "HealthyResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return (
                b'{"frame_protocol":{"version":"ocr.realtime.frame.v1",'
                b'"encoding":"jsonl","content_type":"application/x-ndjson",'
                b'"max_frame_bytes":1048576}}'
            )

    def healthy_urlopen(*args: object, **kwargs: object) -> HealthyResponse:
        return HealthyResponse()

    monkeypatch.setattr(capabilities_route, "urlopen", healthy_urlopen)

    status = await capabilities_route.webtransport_gateway_status(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            webtransport_enabled=True,
            webtransport_url="http://localhost:8081/v1/wt",
            webtransport_health_url="http://localhost:8081/ready",
        )
    )

    assert status.available is True
    assert status.status == "available"


async def test_webtransport_status_rejects_incompatible_gateway_protocol(monkeypatch) -> None:
    class IncompatibleResponse:
        status = 200

        def __enter__(self) -> "IncompatibleResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"frame_protocol":{"version":"legacy","encoding":"jsonl"}}'

    def incompatible_urlopen(*args: object, **kwargs: object) -> IncompatibleResponse:
        return IncompatibleResponse()

    monkeypatch.setattr(capabilities_route, "urlopen", incompatible_urlopen)

    status = await capabilities_route.webtransport_gateway_status(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            webtransport_enabled=True,
            webtransport_url="http://localhost:8081/v1/wt",
            webtransport_health_url="http://localhost:8081/ready",
        )
    )

    assert status.available is False
    assert status.status == "unhealthy"
    assert status.unavailable_reason == "Gateway frame protocol version is incompatible."


async def test_webtransport_status_rejects_small_gateway_frame_limit(monkeypatch) -> None:
    class SmallFrameLimitResponse:
        status = 200

        def __enter__(self) -> "SmallFrameLimitResponse":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return (
                b'{"frame_protocol":{"version":"ocr.realtime.frame.v1",'
                b'"encoding":"jsonl","content_type":"application/x-ndjson",'
                b'"max_frame_bytes":1024}}'
            )

    def small_frame_limit_urlopen(*args: object, **kwargs: object) -> SmallFrameLimitResponse:
        return SmallFrameLimitResponse()

    monkeypatch.setattr(capabilities_route, "urlopen", small_frame_limit_urlopen)

    status = await capabilities_route.webtransport_gateway_status(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            webtransport_enabled=True,
            webtransport_url="http://localhost:8081/v1/wt",
            webtransport_health_url="http://localhost:8081/ready",
        )
    )

    assert status.available is False
    assert status.status == "unhealthy"
    assert status.unavailable_reason == "Gateway frame protocol max frame size is too small."


async def test_webtransport_status_reports_unhealthy_gateway(monkeypatch) -> None:
    def failing_urlopen(*args: object, **kwargs: object) -> None:
        raise OSError("gateway down")

    monkeypatch.setattr(capabilities_route, "urlopen", failing_urlopen)

    status = await capabilities_route.webtransport_gateway_status(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            webtransport_enabled=True,
            webtransport_url="http://localhost:8081/v1/wt",
            webtransport_health_url="http://localhost:8081/ready",
        )
    )

    assert status.available is False
    assert status.status == "unhealthy"
    assert "Gateway readiness check failed" in str(status.unavailable_reason)
