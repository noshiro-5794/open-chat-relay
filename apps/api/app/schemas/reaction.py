from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReactionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emoji: str = Field(min_length=1, max_length=64)


class ReactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    room_id: UUID
    message_id: UUID
    user_id: UUID
    emoji: str
    created_at: datetime
