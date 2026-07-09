from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AttachmentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=1, le=1024 * 1024 * 100)


class AttachmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    room_id: UUID
    message_id: UUID | None
    uploader_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    status: str
    created_at: datetime


class AttachmentUploadIntentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment: AttachmentResponse
    upload_url: str | None = None


class AttachmentDownloadIntentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment: AttachmentResponse
    download_url: str | None = None
    expires_in_seconds: int
