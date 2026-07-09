from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GatewayAuthenticateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=1)


class GatewayAuthenticateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    token_expires_at: datetime


class GatewayCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str = Field(min_length=1)
    command: dict[str, Any]


class GatewayCommandResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frames: list[dict[str, Any]]
