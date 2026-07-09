import asyncio
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import boto3
import redis.asyncio as redis
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSessionDep, SettingsDep, SystemAdminDep
from app.api.v1.routes.capabilities import webtransport_gateway_status
from app.core.config import Settings
from app.models import AuthSession, EventOutbox, EventOutboxStatus, Notification, User
from app.realtime.manager import manager
from app.schemas.audit import SystemAuditLogResponse
from app.schemas.system import (
    SystemComponentStatus,
    SystemConfigResponse,
    SystemMetricsResponse,
    SystemNotificationMetrics,
    SystemOutboxStatus,
    SystemRealtimeMetrics,
    SystemStatusResponse,
    SystemUserResponse,
    SystemUserUpdateRequest,
)
from app.services.audit import list_system_audit_logs, record_system_audit_log

router = APIRouter(prefix="/system", tags=["system"])
AuditLimitQuery = Annotated[int, Query(ge=1, le=500)]


@router.get("/status", response_model=SystemStatusResponse)
async def system_status(
    _system_admin: SystemAdminDep,
    session: DbSessionDep,
    settings: SettingsDep,
) -> SystemStatusResponse:
    components = {
        "database": await database_status(session),
        "redis": await redis_status(settings),
        "storage": await storage_status(settings),
        "webtransport": await webtransport_status(settings),
    }
    outbox = await outbox_status(session)
    active_auth_sessions = await active_auth_session_count(session)
    overall_status = "ok" if all_ok_or_skipped(components) else "degraded"

    return SystemStatusResponse(
        status=overall_status,
        service=settings.project_name,
        version=settings.version,
        environment=settings.environment,
        components=components,
        outbox=outbox,
        active_auth_sessions=active_auth_sessions,
    )


@router.get("/metrics", response_model=SystemMetricsResponse)
async def system_metrics(
    _system_admin: SystemAdminDep,
    session: DbSessionDep,
) -> SystemMetricsResponse:
    return SystemMetricsResponse(
        realtime=SystemRealtimeMetrics(**manager.stats()),
        outbox=await outbox_status(session),
        notifications=await notification_metrics(session),
        active_auth_sessions=await active_auth_session_count(session),
    )


@router.get("/config", response_model=SystemConfigResponse)
async def system_config(
    _system_admin: SystemAdminDep,
    settings: SettingsDep,
) -> SystemConfigResponse:
    return SystemConfigResponse(
        environment=settings.environment,
        debug=settings.debug,
        docs_enabled=settings.effective_docs_enabled(),
        cors_origins=settings.cors_origins,
        max_request_body_bytes=settings.max_request_body_bytes,
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_backend=settings.effective_rate_limit_backend(),
        storage_backend=settings.storage_backend,
        attachment_verification=settings.effective_verify_attachment_uploads(),
        presence_backend=settings.effective_presence_backend(),
        typing_backend=settings.effective_typing_backend(),
        redis_fanout_enabled=settings.effective_realtime_redis_fanout_enabled(),
        redis_signals_enabled=settings.effective_realtime_redis_signals_enabled(),
        webtransport_enabled=settings.webtransport_enabled,
        webtransport_url=settings.webtransport_url,
        webtransport_health_url=settings.webtransport_health_url,
    )


@router.get("/users", response_model=list[SystemUserResponse])
async def list_system_users(
    _system_admin: SystemAdminDep,
    session: DbSessionDep,
) -> list[SystemUserResponse]:
    result = await session.execute(select(User).order_by(User.created_at, User.email))
    return [SystemUserResponse.model_validate(user) for user in result.scalars().all()]


@router.get("/audit-logs", response_model=list[SystemAuditLogResponse])
async def list_system_audit_log_entries(
    _system_admin: SystemAdminDep,
    session: DbSessionDep,
    limit: AuditLimitQuery = 100,
) -> list[SystemAuditLogResponse]:
    audit_logs = await list_system_audit_logs(session, limit=limit)
    return [SystemAuditLogResponse.model_validate(audit_log) for audit_log in audit_logs]


@router.patch("/users/{user_id}", response_model=SystemUserResponse)
async def update_system_user(
    user_id: UUID,
    payload: SystemUserUpdateRequest,
    system_admin: SystemAdminDep,
    session: DbSessionDep,
) -> SystemUserResponse:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    changes: dict[str, dict[str, bool]] = {}

    if payload.is_system_admin is not None and payload.is_system_admin != user.is_system_admin:
        if not payload.is_system_admin:
            await ensure_not_last_active_system_admin(session, user=user)
        changes["is_system_admin"] = {
            "before": user.is_system_admin,
            "after": payload.is_system_admin,
        }
        user.is_system_admin = payload.is_system_admin

    if payload.is_active is not None and payload.is_active != user.is_active:
        if not payload.is_active:
            await ensure_not_last_active_system_admin(session, user=user)
        changes["is_active"] = {
            "before": user.is_active,
            "after": payload.is_active,
        }
        user.is_active = payload.is_active

    if changes:
        await record_system_audit_log(
            session,
            actor_id=system_admin.id,
            action="system.user_updated",
            target_type="user",
            target_id=user.id,
            details={
                "changes": changes,
                "target_email": user.email,
            },
        )

    await session.commit()
    await session.refresh(user)
    return SystemUserResponse.model_validate(user)


async def database_status(session: AsyncSession) -> SystemComponentStatus:
    try:
        await session.execute(text("select 1"))
    except Exception as exc:
        return SystemComponentStatus(status="unavailable", detail=str(exc))
    return SystemComponentStatus(status="ok")


async def redis_status(settings: Settings) -> SystemComponentStatus:
    if settings.environment == "test":
        return SystemComponentStatus(status="skipped", detail="Redis is skipped in tests.")

    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis_client.ping()
    except Exception as exc:
        return SystemComponentStatus(status="unavailable", detail=str(exc))
    finally:
        await redis_client.aclose()

    return SystemComponentStatus(status="ok")


async def storage_status(settings: Settings) -> SystemComponentStatus:
    if settings.storage_backend == "none":
        return SystemComponentStatus(status="disabled")
    if settings.environment == "test":
        return SystemComponentStatus(status="skipped", detail="Storage is skipped in tests.")

    def check_bucket() -> SystemComponentStatus:
        client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region_name,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
        except (BotoCoreError, ClientError) as exc:
            return SystemComponentStatus(status="unavailable", detail=str(exc))
        return SystemComponentStatus(status="ok")

    return await asyncio.to_thread(check_bucket)


async def webtransport_status(settings: Settings) -> SystemComponentStatus:
    status = await webtransport_gateway_status(settings)
    if status.status == "available":
        return SystemComponentStatus(status="ok")
    if status.status == "disabled":
        return SystemComponentStatus(status="disabled", detail=status.unavailable_reason)
    return SystemComponentStatus(status="unavailable", detail=status.unavailable_reason)


async def outbox_status(session: AsyncSession) -> SystemOutboxStatus:
    pending_result = await session.execute(
        select(func.count())
        .select_from(EventOutbox)
        .where(EventOutbox.status == EventOutboxStatus.PENDING.value)
    )
    failed_result = await session.execute(
        select(func.count())
        .select_from(EventOutbox)
        .where(EventOutbox.status == EventOutboxStatus.FAILED.value)
    )
    return SystemOutboxStatus(
        pending=pending_result.scalar_one(),
        failed=failed_result.scalar_one(),
    )


async def active_auth_session_count(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(AuthSession)
        .where(
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )
    return result.scalar_one()


async def notification_metrics(session: AsyncSession) -> SystemNotificationMetrics:
    total_result = await session.execute(select(func.count()).select_from(Notification))
    unread_result = await session.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.read_at.is_(None))
    )
    return SystemNotificationMetrics(
        total=total_result.scalar_one(),
        unread=unread_result.scalar_one(),
    )


async def ensure_not_last_active_system_admin(session: AsyncSession, *, user: User) -> None:
    if not user.is_system_admin or not user.is_active:
        return

    result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(
            User.is_system_admin.is_(True),
            User.is_active.is_(True),
        )
    )
    if result.scalar_one() <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one active system administrator is required.",
        )


def all_ok_or_skipped(components: dict[str, SystemComponentStatus]) -> bool:
    return all(
        component.status in {"ok", "skipped", "disabled"} for component in components.values()
    )
