from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    workspace_id: UUID
    actor_id: UUID | None
    actor_type: str
    action: str
    target_type: str
    target_id: UUID | None
    details: dict[str, Any]
    created_at: datetime


class SystemAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    actor_id: UUID | None
    actor_type: str
    action: str
    target_type: str
    target_id: UUID | None
    details: dict[str, Any]
    created_at: datetime
