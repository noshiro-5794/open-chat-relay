from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Room, RoomMember, RoomRole, User, Workspace, WorkspaceRole
from app.services.auth import get_user_by_email
from app.services.workspace import (
    RoomWithRole,
    SlugAlreadyExistsError,
    UserNotFoundError,
    create_room,
    ensure_workspace_membership,
    invite_room_member_by_email,
    start_direct_conversation,
)

CONVERSATION_WORKSPACE_SLUG = "openchatrelay-network"
CONVERSATION_WORKSPACE_NAME = "OpenChatRelay Network"


async def list_conversations(session: AsyncSession, *, user: User) -> list[RoomWithRole]:
    workspace = await ensure_conversation_workspace(session, user=user)
    room_member_counts = (
        select(
            RoomMember.room_id.label("room_id"),
            func.count(RoomMember.id).label("member_count"),
        )
        .group_by(RoomMember.room_id)
        .subquery()
    )
    statement = (
        select(Room, RoomMember.role)
        .join(RoomMember, (RoomMember.room_id == Room.id) & (RoomMember.user_id == user.id))
        .outerjoin(room_member_counts, room_member_counts.c.room_id == Room.id)
        .where(
            Room.workspace_id == workspace.id,
            RoomMember.user_id == user.id,
            or_(
                Room.is_private.is_(False),
                func.coalesce(room_member_counts.c.member_count, 0) > 1,
            )
        )
        .order_by(Room.created_at)
    )
    result = await session.execute(statement)
    return [RoomWithRole(room=room, role=role) for room, role in result.all()]


async def start_global_direct_conversation(
    session: AsyncSession,
    *,
    actor: User,
    target_email: str,
) -> RoomWithRole:
    workspace = await ensure_conversation_workspace(session, user=actor)
    return await start_direct_conversation(
        session,
        actor=actor,
        workspace_id=workspace.id,
        target_email=target_email,
    )


async def create_group_conversation(
    session: AsyncSession,
    *,
    actor: User,
    name: str,
    member_emails: list[str],
) -> RoomWithRole:
    workspace = await ensure_conversation_workspace(session, user=actor)
    invite_emails = await validate_group_invite_emails(
        session,
        actor=actor,
        member_emails=member_emails,
    )
    room = await create_room(
        session,
        user=actor,
        workspace_id=workspace.id,
        name=name,
        slug=f"group-{uuid4().hex[:12]}",
        is_private=False,
    )
    for email in invite_emails:
        await invite_room_member_by_email(
            session,
            actor=actor,
            room_id=room.room.id,
            email=email,
            role=RoomRole.MEMBER.value,
        )
    return room


async def validate_group_invite_emails(
    session: AsyncSession,
    *,
    actor: User,
    member_emails: list[str],
) -> list[str]:
    invite_emails: list[str] = []
    seen_emails: set[str] = set()
    for email in member_emails:
        normalized_email = email.strip().lower()
        if normalized_email == "" or normalized_email == actor.email.lower():
            continue
        if normalized_email in seen_emails:
            continue

        user = await get_user_by_email(session, normalized_email)
        if user is None or not user.is_active:
            raise UserNotFoundError

        seen_emails.add(normalized_email)
        invite_emails.append(normalized_email)
    return invite_emails


async def ensure_conversation_workspace(session: AsyncSession, *, user: User) -> Workspace:
    result = await session.execute(
        select(Workspace).where(Workspace.slug == CONVERSATION_WORKSPACE_SLUG)
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        workspace = Workspace(
            name=CONVERSATION_WORKSPACE_NAME,
            slug=CONVERSATION_WORKSPACE_SLUG,
        )
        session.add(workspace)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise SlugAlreadyExistsError from exc

    await ensure_workspace_membership(
        session,
        workspace_id=workspace.id,
        user_id=user.id,
        role=WorkspaceRole.MEMBER.value,
    )
    await session.commit()
    await session.refresh(workspace)
    return workspace


def selected_conversation_id(conversations: list[RoomWithRole]) -> UUID | None:
    return conversations[0].room.id if conversations else None
