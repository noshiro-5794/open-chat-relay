from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.realtime.policies import DeliveryPolicy


class CommandEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    request_id: str | None = None
    workspace_id: str | None = None
    room_id: str | None = None
    lane: str = "command"
    data: dict[str, Any] = Field(default_factory=dict)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    workspace_id: str
    room_id: str | None = None
    actor_id: str | None = None
    room_event_seq: int | None = None
    workspace_event_seq: int | None = None
    created_at: datetime
    delivery: DeliveryPolicy
    data: dict[str, Any] = Field(default_factory=dict)


class AckEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "ack"
    request_id: str
    status: str = "ok"
    event_id: str | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = "error"
    request_id: str | None = None
    code: str
    message: str
