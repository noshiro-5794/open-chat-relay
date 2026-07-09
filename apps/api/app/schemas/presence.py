from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PresenceUserResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    status: str


class RoomPresenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: UUID
    users: list[PresenceUserResponse]
