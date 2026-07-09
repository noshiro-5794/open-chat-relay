from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SystemComponentStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded", "unavailable", "skipped", "disabled"]
    detail: str | None = None


class SystemOutboxStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending: int
    failed: int


class SystemStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    components: dict[str, SystemComponentStatus]
    outbox: SystemOutboxStatus
    active_auth_sessions: int


class SystemRealtimeMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_connections: int
    active_users: int
    subscribed_rooms: int
    room_subscriptions: int


class SystemNotificationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    unread: int


class SystemMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    realtime: SystemRealtimeMetrics
    outbox: SystemOutboxStatus
    notifications: SystemNotificationMetrics
    active_auth_sessions: int


class SystemConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment: str
    debug: bool
    docs_enabled: bool
    cors_origins: list[str]
    max_request_body_bytes: int
    rate_limit_enabled: bool
    rate_limit_backend: str
    storage_backend: str
    attachment_verification: bool
    presence_backend: str
    typing_backend: str
    redis_fanout_enabled: bool
    redis_signals_enabled: bool
    webtransport_enabled: bool
    webtransport_url: str | None
    webtransport_health_url: str | None


class SystemUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    email: str
    display_name: str
    is_active: bool
    is_system_admin: bool
    created_at: datetime
    updated_at: datetime


class SystemUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool | None = Field(default=None)
    is_system_admin: bool | None = Field(default=None)
