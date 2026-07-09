from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AppCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=80)


class BotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    app_id: UUID
    created_by_id: UUID
    display_name: str
    slug: str
    created_at: datetime


class AppResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    created_by_id: UUID
    name: str
    slug: str
    created_at: datetime
    bot: BotResponse | None = None


class ApiKeyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class IncomingWebhookCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    room_id: UUID


class ApiKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    app_id: UUID
    created_by_id: UUID
    name: str
    key_prefix: str
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class IncomingWebhookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    app_id: UUID
    bot_id: UUID
    room_id: UUID
    created_by_id: UUID
    name: str
    secret_prefix: str
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class CreatedApiKeyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: ApiKeyResponse
    secret: str


class CreatedIncomingWebhookResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    webhook: IncomingWebhookResponse
    secret: str
    delivery_url: str
