from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FriendAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)


class FriendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    user_id: UUID
    email: str
    display_name: str
    created_at: datetime
