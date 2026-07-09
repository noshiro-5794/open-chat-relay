from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TypingUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    status: str = "started"


class RoomTypingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: UUID
    users: list[TypingUserResponse]
