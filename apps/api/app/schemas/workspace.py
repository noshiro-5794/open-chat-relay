from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    name: str
    slug: str
    role: str


class WorkspaceMemberAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    role: Literal["owner", "member"] = "member"


class WorkspaceMemberUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["owner", "member"]


class WorkspaceMemberResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    workspace_id: UUID
    user_id: UUID
    email: str
    display_name: str
    role: str


class RoomCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    is_private: bool = False


class RoomMemberAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    role: Literal["owner", "member"] = "member"


class DirectConversationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)


class RoomMemberInviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    role: Literal["owner", "member"] = "member"


class RoomMemberUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["owner", "member"]


class RoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    name: str
    slug: str
    is_private: bool
    role: str | None = None


class RoomMemberResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    room_id: UUID
    user_id: UUID
    email: str
    display_name: str
    role: str


class MembershipStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    room: RoomResponse
