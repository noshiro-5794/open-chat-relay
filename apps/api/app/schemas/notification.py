from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    user_id: UUID
    workspace_id: UUID
    room_id: UUID | None
    event_id: UUID
    notification_type: str
    title: str
    body: str
    payload: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class UnreadNotificationCountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unread_count: int
