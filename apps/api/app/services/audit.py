from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, SystemAuditLog


async def record_audit_log(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    actor_id: UUID | None,
    action: str,
    target_type: str,
    target_id: UUID | None,
    details: dict[str, Any] | None = None,
    actor_type: str = "user",
) -> AuditLog:
    audit_log = AuditLog(
        workspace_id=workspace_id,
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    )
    session.add(audit_log)
    return audit_log


async def list_workspace_audit_logs(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    limit: int,
) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.workspace_id == workspace_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def record_system_audit_log(
    session: AsyncSession,
    *,
    actor_id: UUID | None,
    action: str,
    target_type: str,
    target_id: UUID | None,
    details: dict[str, Any] | None = None,
    actor_type: str = "user",
) -> SystemAuditLog:
    audit_log = SystemAuditLog(
        actor_id=actor_id,
        actor_type=actor_type,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    )
    session.add(audit_log)
    return audit_log


async def list_system_audit_logs(session: AsyncSession, *, limit: int) -> list[SystemAuditLog]:
    result = await session.execute(
        select(SystemAuditLog).order_by(SystemAuditLog.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
