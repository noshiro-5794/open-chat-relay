from typing import Literal

from pydantic import BaseModel, ConfigDict


class TransportCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    status: Literal["available", "disabled", "unhealthy"]
    unavailable_reason: str | None = None
    url: str | None
    experimental: bool
    priority: int
    mode: Literal["bidirectional", "server_stream"]
    supports_reliable_streams: bool
    supports_datagrams: bool
    supports_session_resume: bool
    fallback_to: str | None = None


class TransportNegotiation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    preferred_order: list[str]
    fallback_policy: Literal["first_available", "strict"] = "first_available"
    resume_parameter: str = "last_event_seq"


class FeatureCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    durable_events: bool
    ephemeral_signals: bool
    session_resume: bool
    incoming_webhooks: bool
    read_states: bool
    membership_management: bool
    message_replies: bool
    message_search: bool
    audit_logs: bool
    attachment_verification: bool
    event_outbox: bool
    datagrams: bool
    notification_inbox: bool


class ProtocolCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    realtime_commands: list[str]
    event_types: list[str]


class RealtimeFrameCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    encoding: Literal["jsonl"]
    content_type: str
    delimiter: str
    max_frame_bytes: int


class CapabilitiesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transports: dict[str, TransportCapability]
    transport_negotiation: TransportNegotiation
    features: FeatureCapabilities
    protocol: ProtocolCapabilities
    realtime_frame: RealtimeFrameCapabilities
