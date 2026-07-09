from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    api_key_prefix,
    create_api_key_secret,
    create_webhook_secret,
    hash_api_key,
)
from app.models import ApiKey, App, Bot, IncomingWebhook, Room, User, WorkspaceRole
from app.services.audit import record_audit_log
from app.services.workspace import (
    RoomNotFoundError,
    WorkspaceNotFoundError,
    get_workspace_for_user,
    normalize_slug,
)


class WorkspaceOwnerRequiredError(Exception):
    """Raised when a user needs owner privileges in a workspace."""


class AppNotFoundError(Exception):
    """Raised when an app does not exist or is not visible to the user."""


class AppSlugAlreadyExistsError(Exception):
    """Raised when an app slug already exists in the workspace."""


class ApiKeyNotFoundError(Exception):
    """Raised when an API key does not exist or is not visible to the user."""


class IncomingWebhookNotFoundError(Exception):
    """Raised when an incoming webhook does not exist or is not visible."""


class BotNotFoundError(Exception):
    """Raised when an app bot identity is missing."""


@dataclass(frozen=True)
class CreatedApiKey:
    api_key: ApiKey
    secret: str


@dataclass(frozen=True)
class CreatedIncomingWebhook:
    webhook: IncomingWebhook
    secret: str


async def create_app(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
    name: str,
    slug: str | None,
) -> App:
    await require_workspace_owner(session, user=user, workspace_id=workspace_id)
    app = App(
        workspace_id=workspace_id,
        created_by_id=user.id,
        name=name.strip(),
        slug=normalize_slug(slug or name),
    )
    session.add(app)
    try:
        await session.flush()
        session.add(
            Bot(
                workspace_id=app.workspace_id,
                app_id=app.id,
                created_by_id=user.id,
                display_name=app.name,
                slug=app.slug,
            )
        )
        await record_audit_log(
            session,
            workspace_id=app.workspace_id,
            actor_id=user.id,
            action="app.created",
            target_type="app",
            target_id=app.id,
            details={"name": app.name, "slug": app.slug},
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppSlugAlreadyExistsError from exc

    await session.refresh(app)
    return app


async def list_workspace_apps(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
) -> list[App]:
    await require_workspace_owner(session, user=user, workspace_id=workspace_id)
    result = await session.execute(
        select(App).where(App.workspace_id == workspace_id).order_by(App.created_at)
    )
    return list(result.scalars().all())


async def get_app_for_owner(session: AsyncSession, *, user: User, app_id: UUID) -> App:
    result = await session.execute(select(App).where(App.id == app_id))
    app = result.scalar_one_or_none()
    if app is None:
        raise AppNotFoundError

    await require_workspace_owner(session, user=user, workspace_id=app.workspace_id)
    return app


async def create_api_key(
    session: AsyncSession,
    *,
    user: User,
    app_id: UUID,
    name: str,
) -> CreatedApiKey:
    app = await get_app_for_owner(session, user=user, app_id=app_id)
    secret = create_api_key_secret()
    api_key = ApiKey(
        workspace_id=app.workspace_id,
        app_id=app.id,
        created_by_id=user.id,
        name=name.strip(),
        key_prefix=api_key_prefix(secret),
        key_hash=hash_api_key(secret),
    )
    session.add(api_key)
    await session.flush()
    await record_audit_log(
        session,
        workspace_id=app.workspace_id,
        actor_id=user.id,
        action="api_key.created",
        target_type="api_key",
        target_id=api_key.id,
        details={"app_id": str(app.id), "name": api_key.name, "key_prefix": api_key.key_prefix},
    )
    await session.commit()
    await session.refresh(api_key)
    return CreatedApiKey(api_key=api_key, secret=secret)


async def create_incoming_webhook(
    session: AsyncSession,
    *,
    user: User,
    app_id: UUID,
    room_id: UUID,
    name: str,
) -> CreatedIncomingWebhook:
    app = await get_app_for_owner(session, user=user, app_id=app_id)
    bot = await get_bot_for_app(session, app_id=app.id)
    room = await session.get(Room, room_id)
    if room is None or room.workspace_id != app.workspace_id:
        raise RoomNotFoundError

    secret = create_webhook_secret()
    webhook = IncomingWebhook(
        workspace_id=app.workspace_id,
        app_id=app.id,
        bot_id=bot.id,
        room_id=room.id,
        created_by_id=user.id,
        name=name.strip(),
        secret_prefix=api_key_prefix(secret),
        secret_hash=hash_api_key(secret),
    )
    session.add(webhook)
    await session.flush()
    await record_audit_log(
        session,
        workspace_id=app.workspace_id,
        actor_id=user.id,
        action="incoming_webhook.created",
        target_type="incoming_webhook",
        target_id=webhook.id,
        details={
            "app_id": str(app.id),
            "room_id": str(room.id),
            "name": webhook.name,
            "secret_prefix": webhook.secret_prefix,
        },
    )
    await session.commit()
    await session.refresh(webhook)
    return CreatedIncomingWebhook(webhook=webhook, secret=secret)


async def get_bot_for_app(session: AsyncSession, *, app_id: UUID) -> Bot:
    result = await session.execute(select(Bot).where(Bot.app_id == app_id))
    bot = result.scalar_one_or_none()
    if bot is None:
        raise BotNotFoundError
    return bot


async def list_incoming_webhooks(
    session: AsyncSession,
    *,
    user: User,
    app_id: UUID,
) -> list[IncomingWebhook]:
    app = await get_app_for_owner(session, user=user, app_id=app_id)
    result = await session.execute(
        select(IncomingWebhook)
        .where(IncomingWebhook.app_id == app.id)
        .order_by(IncomingWebhook.created_at)
    )
    return list(result.scalars().all())


async def revoke_incoming_webhook(
    session: AsyncSession,
    *,
    user: User,
    app_id: UUID,
    webhook_id: UUID,
) -> IncomingWebhook:
    app = await get_app_for_owner(session, user=user, app_id=app_id)
    result = await session.execute(
        select(IncomingWebhook).where(
            IncomingWebhook.id == webhook_id,
            IncomingWebhook.app_id == app.id,
        )
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise IncomingWebhookNotFoundError

    if webhook.revoked_at is None:
        webhook.revoked_at = datetime.now(UTC)
        await record_audit_log(
            session,
            workspace_id=app.workspace_id,
            actor_id=user.id,
            action="incoming_webhook.revoked",
            target_type="incoming_webhook",
            target_id=webhook.id,
            details={"app_id": str(app.id), "name": webhook.name},
        )
        await session.commit()
        await session.refresh(webhook)

    return webhook


async def authenticate_incoming_webhook(
    session: AsyncSession,
    *,
    webhook_id: UUID,
    secret: str,
) -> IncomingWebhook | None:
    result = await session.execute(
        select(IncomingWebhook).where(
            IncomingWebhook.id == webhook_id,
            IncomingWebhook.secret_hash == hash_api_key(secret),
            IncomingWebhook.revoked_at.is_(None),
        )
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        return None

    webhook.last_used_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(webhook)
    return webhook


async def list_api_keys(session: AsyncSession, *, user: User, app_id: UUID) -> list[ApiKey]:
    app = await get_app_for_owner(session, user=user, app_id=app_id)
    result = await session.execute(
        select(ApiKey).where(ApiKey.app_id == app.id).order_by(ApiKey.created_at)
    )
    return list(result.scalars().all())


async def revoke_api_key(
    session: AsyncSession,
    *,
    user: User,
    app_id: UUID,
    api_key_id: UUID,
) -> ApiKey:
    app = await get_app_for_owner(session, user=user, app_id=app_id)
    result = await session.execute(
        select(ApiKey).where(ApiKey.id == api_key_id, ApiKey.app_id == app.id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise ApiKeyNotFoundError

    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(UTC)
        await record_audit_log(
            session,
            workspace_id=app.workspace_id,
            actor_id=user.id,
            action="api_key.revoked",
            target_type="api_key",
            target_id=api_key.id,
            details={"app_id": str(app.id), "name": api_key.name, "key_prefix": api_key.key_prefix},
        )
        await session.commit()
        await session.refresh(api_key)

    return api_key


async def authenticate_api_key(session: AsyncSession, *, secret: str) -> ApiKey | None:
    result = await session.execute(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(secret), ApiKey.revoked_at.is_(None))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        return None

    api_key.last_used_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(api_key)
    return api_key


async def require_workspace_owner(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
) -> None:
    try:
        workspace = await get_workspace_for_user(session, user=user, workspace_id=workspace_id)
    except WorkspaceNotFoundError:
        raise

    if workspace.role != WorkspaceRole.OWNER.value:
        raise WorkspaceOwnerRequiredError
