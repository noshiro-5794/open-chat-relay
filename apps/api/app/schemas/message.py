from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.attachment import AttachmentResponse


class MessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(default="", max_length=8000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=20)
    reply_to_id: UUID | None = None

    @model_validator(mode="after")
    def require_content_or_attachment(self) -> "MessageCreateRequest":
        if not self.content.strip() and not self.attachment_ids:
            raise ValueError("Message requires content or at least one attachment.")
        return self


class MessageUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8000)


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    room_id: UUID
    sender_type: str
    sender_id: UUID | None
    sender_bot_id: UUID | None
    message_type: str
    content: str
    reply_to_id: UUID | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    attachments: list[AttachmentResponse] = Field(default_factory=list)


class MessagePageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MessageResponse]
    next_before_message_id: UUID | None = None
    has_more: bool


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    type: str
    workspace_id: UUID
    room_id: UUID | None
    actor_type: str
    actor_id: UUID | None
    actor_bot_id: UUID | None
    room_event_seq: int | None
    workspace_event_seq: int
    lane: str
    reliability: str
    ordering: str
    priority: str
    ttl_ms: int | None
    created_at: datetime
    data: dict[str, Any]
