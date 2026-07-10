from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.workspace import RoomResponse


class DirectConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)


class GroupConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    member_emails: list[str] = Field(default_factory=list, max_length=50)


class ConversationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversations: list[RoomResponse]
    selected_conversation_id: UUID | None = None
