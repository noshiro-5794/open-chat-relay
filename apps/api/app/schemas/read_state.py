from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RoomReadStateUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    last_read_event_seq: int = Field(ge=0)


class RoomReadStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    room_id: UUID
    user_id: UUID
    last_read_event_seq: int
    created_at: datetime
    updated_at: datetime
