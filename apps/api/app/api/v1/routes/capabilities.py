import asyncio
import json
from dataclasses import dataclass
from typing import Literal
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import APIRouter

from app.api.deps import SettingsDep
from app.core.config import Settings
from app.realtime.protocol import PROTOCOL_VERSION, SUPPORTED_COMMANDS, SUPPORTED_EVENT_TYPES
from app.schemas.capabilities import (
    CapabilitiesResponse,
    FeatureCapabilities,
    ProtocolCapabilities,
    RealtimeFrameCapabilities,
    TransportCapability,
    TransportNegotiation,
)

router = APIRouter()
EXPECTED_FRAME_PROTOCOL_VERSION = "ocr.realtime.frame.v1"
EXPECTED_FRAME_ENCODING = "jsonl"
EXPECTED_FRAME_CONTENT_TYPE = "application/x-ndjson"


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities(settings: SettingsDep) -> CapabilitiesResponse:
    webtransport = await webtransport_gateway_status(settings)
    return CapabilitiesResponse(
        transports={
            "websocket": TransportCapability(
                available=True,
                status="available",
                unavailable_reason=None,
                url="/v1/ws",
                experimental=False,
                priority=20,
                mode="bidirectional",
                supports_reliable_streams=True,
                supports_datagrams=False,
                supports_session_resume=True,
                fallback_to="sse",
            ),
            "webtransport": TransportCapability(
                available=webtransport.available,
                status=webtransport.status,
                unavailable_reason=webtransport.unavailable_reason,
                url=settings.webtransport_url,
                experimental=True,
                priority=10,
                mode="bidirectional",
                supports_reliable_streams=True,
                supports_datagrams=webtransport.available,
                supports_session_resume=True,
                fallback_to="websocket",
            ),
            "sse": TransportCapability(
                available=True,
                status="available",
                unavailable_reason=None,
                url="/v1/events/stream",
                experimental=False,
                priority=30,
                mode="server_stream",
                supports_reliable_streams=False,
                supports_datagrams=False,
                supports_session_resume=True,
                fallback_to=None,
            ),
        },
        transport_negotiation=TransportNegotiation(
            version="ocr.transport.v1",
            preferred_order=["webtransport", "websocket", "sse"],
            fallback_policy="first_available",
            resume_parameter="last_event_seq",
        ),
        features=FeatureCapabilities(
            durable_events=True,
            ephemeral_signals=True,
            session_resume=True,
            incoming_webhooks=True,
            read_states=True,
            membership_management=True,
            message_replies=True,
            message_search=True,
            audit_logs=True,
            attachment_verification=settings.effective_verify_attachment_uploads(),
            event_outbox=True,
            datagrams=webtransport.available,
            notification_inbox=True,
        ),
        protocol=ProtocolCapabilities(
            version=PROTOCOL_VERSION,
            realtime_commands=SUPPORTED_COMMANDS,
            event_types=SUPPORTED_EVENT_TYPES,
        ),
        realtime_frame=RealtimeFrameCapabilities(
            version="ocr.realtime.frame.v1",
            encoding="jsonl",
            content_type="application/x-ndjson",
            delimiter="\n",
            max_frame_bytes=settings.max_request_body_bytes,
        ),
    )


@dataclass(frozen=True)
class WebTransportGatewayStatus:
    available: bool
    status: Literal["available", "disabled", "unhealthy"]
    unavailable_reason: str | None


async def webtransport_gateway_status(settings: Settings) -> WebTransportGatewayStatus:
    if not settings.webtransport_enabled:
        return WebTransportGatewayStatus(
            available=False,
            status="disabled",
            unavailable_reason="WebTransport is disabled by configuration.",
        )

    if settings.webtransport_url is None:
        return WebTransportGatewayStatus(
            available=False,
            status="unhealthy",
            unavailable_reason="WebTransport URL is not configured.",
        )

    if settings.webtransport_health_url is None:
        return WebTransportGatewayStatus(
            available=True,
            status="available",
            unavailable_reason=None,
        )

    healthy, reason = await probe_webtransport_gateway(settings)
    if healthy:
        return WebTransportGatewayStatus(
            available=True,
            status="available",
            unavailable_reason=None,
        )

    return WebTransportGatewayStatus(
        available=False,
        status="unhealthy",
        unavailable_reason=reason,
    )


async def probe_webtransport_gateway(settings: Settings) -> tuple[bool, str | None]:
    assert settings.webtransport_health_url is not None
    parsed_url = urlparse(settings.webtransport_health_url)
    if parsed_url.scheme not in {"http", "https"}:
        return False, "Gateway readiness URL must use http or https."

    def check() -> tuple[bool, str | None]:
        request = Request(settings.webtransport_health_url, method="GET")  # noqa: S310
        try:
            with urlopen(  # noqa: S310
                request,
                timeout=settings.webtransport_health_timeout_seconds,
            ) as response:
                if not 200 <= response.status < 300:
                    return False, f"Gateway readiness returned HTTP {response.status}."
                try:
                    body = json.loads(response.read().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return False, "Gateway readiness did not return valid JSON."

                frame_protocol = body.get("frame_protocol")
                if not isinstance(frame_protocol, dict):
                    return False, "Gateway readiness did not include frame protocol metadata."
                if frame_protocol.get("version") != EXPECTED_FRAME_PROTOCOL_VERSION:
                    return False, "Gateway frame protocol version is incompatible."
                if frame_protocol.get("encoding") != EXPECTED_FRAME_ENCODING:
                    return False, "Gateway frame protocol encoding is incompatible."
                if frame_protocol.get("content_type") != EXPECTED_FRAME_CONTENT_TYPE:
                    return False, "Gateway frame protocol content type is incompatible."
                gateway_max_frame_bytes = frame_protocol.get("max_frame_bytes")
                if not isinstance(gateway_max_frame_bytes, int):
                    return False, "Gateway frame protocol max frame size is missing."
                if gateway_max_frame_bytes < settings.max_request_body_bytes:
                    return False, "Gateway frame protocol max frame size is too small."
                return True, None
        except (OSError, URLError) as exc:
            return False, f"Gateway readiness check failed: {exc}."

    return await asyncio.to_thread(check)
