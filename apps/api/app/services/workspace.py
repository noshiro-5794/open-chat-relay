import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Membership, Room, RoomMember, RoomRole, User, Workspace, WorkspaceRole
from app.services.audit import record_audit_log

_slug_pattern = re.compile(r"[^a-z0-9]+")


class WorkspaceNotFoundError(Exception):
    """Raised when the workspace does not exist or the user cannot access it."""


class RoomNotFoundError(Exception):
    """Raised when the room does not exist or the user cannot access it."""


class SlugAlreadyExistsError(Exception):
    """Raised when a workspace or room slug conflicts with an existing record."""


class WorkspaceOwnerRequiredError(Exception):
    """Raised when a user needs owner privileges in a workspace."""


class WorkspaceMemberNotFoundError(Exception):
    """Raised when a workspace membership cannot be found."""


class WorkspaceLastOwnerError(Exception):
    """Raised when an operation would remove the final workspace owner."""


class RoomOwnerRequiredError(Exception):
    """Raised when a user needs owner privileges in a room."""


class RoomMemberNotFoundError(Exception):
    """Raised when a room membership cannot be found."""


class RoomLastOwnerError(Exception):
    """Raised when an operation would remove the final room owner."""


class UserNotFoundError(Exception):
    """Raised when a user cannot be found."""


class WorkspaceMembershipRequiredError(Exception):
    """Raised when a user must be a workspace member before a room operation."""


@dataclass(frozen=True)
class WorkspaceWithRole:
    workspace: Workspace
    role: str


@dataclass(frozen=True)
class MembershipWithUser:
    membership: Membership
    user: User


@dataclass(frozen=True)
class RoomWithRole:
    room: Room
    role: str | None


@dataclass(frozen=True)
class RoomMemberWithUser:
    room_member: RoomMember
    user: User


async def create_workspace(
    session: AsyncSession,
    *,
    user: User,
    name: str,
    slug: str | None,
) -> WorkspaceWithRole:
    workspace = Workspace(name=name.strip(), slug=normalize_slug(slug or name))
    try:
        session.add(workspace)
        await session.flush()

        session.add(
            Membership(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.OWNER.value,
            )
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise SlugAlreadyExistsError from exc

    await session.refresh(workspace)
    return WorkspaceWithRole(workspace=workspace, role=WorkspaceRole.OWNER.value)


async def list_workspaces(session: AsyncSession, *, user: User) -> list[WorkspaceWithRole]:
    statement = (
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.created_at)
    )
    result = await session.execute(statement)
    return [WorkspaceWithRole(workspace=workspace, role=role) for workspace, role in result.all()]


async def get_workspace_for_user(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
) -> WorkspaceWithRole:
    statement = (
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Workspace.id == workspace_id, Membership.user_id == user.id)
    )
    result = await session.execute(statement)
    row = result.one_or_none()
    if row is None:
        raise WorkspaceNotFoundError
    workspace, role = row
    return WorkspaceWithRole(workspace=workspace, role=role)


async def list_workspace_members(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
) -> list[MembershipWithUser]:
    await get_workspace_for_user(session, user=user, workspace_id=workspace_id)
    result = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace_id)
        .order_by(User.display_name, User.email)
    )
    return [
        MembershipWithUser(membership=membership, user=member_user)
        for membership, member_user in result.all()
    ]


async def add_workspace_member(
    session: AsyncSession,
    *,
    actor: User,
    workspace_id: UUID,
    email: str,
    role: str,
) -> MembershipWithUser:
    await require_workspace_owner(session, user=actor, workspace_id=workspace_id)

    result = await session.execute(select(User).where(User.email == email.strip().lower()))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFoundError

    result = await session.execute(
        select(Membership).where(
            Membership.workspace_id == workspace_id,
            Membership.user_id == user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        membership = Membership(workspace_id=workspace_id, user_id=user.id, role=role)
        session.add(membership)
    else:
        membership.role = role
    await session.flush()
    await record_audit_log(
        session,
        workspace_id=workspace_id,
        actor_id=actor.id,
        action="workspace.member_upserted",
        target_type="membership",
        target_id=membership.id,
        details={
            "user_id": str(user.id),
            "email": user.email,
            "role": role,
        },
    )

    await session.commit()
    await session.refresh(membership)
    return MembershipWithUser(membership=membership, user=user)


async def update_workspace_member_role(
    session: AsyncSession,
    *,
    actor: User,
    workspace_id: UUID,
    user_id: UUID,
    role: str,
) -> MembershipWithUser:
    await require_workspace_owner(session, user=actor, workspace_id=workspace_id)
    membership_with_user = await get_workspace_membership_with_user(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    if (
        membership_with_user.membership.role == WorkspaceRole.OWNER.value
        and role != WorkspaceRole.OWNER.value
    ):
        await ensure_workspace_has_another_owner(
            session,
            workspace_id=workspace_id,
            user_id=user_id,
        )

    membership_with_user.membership.role = role
    await session.flush()
    await record_audit_log(
        session,
        workspace_id=workspace_id,
        actor_id=actor.id,
        action="workspace.member_role_updated",
        target_type="membership",
        target_id=membership_with_user.membership.id,
        details={
            "user_id": str(user_id),
            "email": membership_with_user.user.email,
            "role": role,
        },
    )
    await session.commit()
    await session.refresh(membership_with_user.membership)
    return membership_with_user


async def remove_workspace_member(
    session: AsyncSession,
    *,
    actor: User,
    workspace_id: UUID,
    user_id: UUID,
) -> None:
    await require_workspace_owner(session, user=actor, workspace_id=workspace_id)
    membership_with_user = await get_workspace_membership_with_user(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
    )
    if membership_with_user.membership.role == WorkspaceRole.OWNER.value:
        await ensure_workspace_has_another_owner(
            session,
            workspace_id=workspace_id,
            user_id=user_id,
        )

    workspace_room_ids = select(Room.id).where(Room.workspace_id == workspace_id)
    await session.execute(
        delete(RoomMember).where(
            RoomMember.room_id.in_(workspace_room_ids),
            RoomMember.user_id == user_id,
        )
    )
    await session.delete(membership_with_user.membership)
    await record_audit_log(
        session,
        workspace_id=workspace_id,
        actor_id=actor.id,
        action="workspace.member_removed",
        target_type="membership",
        target_id=membership_with_user.membership.id,
        details={
            "user_id": str(user_id),
            "email": membership_with_user.user.email,
        },
    )
    await session.commit()


async def create_room(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
    name: str,
    slug: str | None,
    is_private: bool,
) -> RoomWithRole:
    await get_workspace_for_user(session, user=user, workspace_id=workspace_id)

    room = Room(
        workspace_id=workspace_id,
        name=name.strip(),
        slug=normalize_slug(slug or name),
        is_private=is_private,
    )
    try:
        session.add(room)
        await session.flush()

        session.add(
            RoomMember(
                room_id=room.id,
                user_id=user.id,
                role=RoomRole.OWNER.value,
            )
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise SlugAlreadyExistsError from exc

    await session.refresh(room)
    return RoomWithRole(room=room, role=RoomRole.OWNER.value)


async def list_rooms(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
) -> list[RoomWithRole]:
    await get_workspace_for_user(session, user=user, workspace_id=workspace_id)

    statement = (
        select(Room, RoomMember.role)
        .outerjoin(
            RoomMember,
            (RoomMember.room_id == Room.id) & (RoomMember.user_id == user.id),
        )
        .where(Room.workspace_id == workspace_id)
        .order_by(Room.created_at)
    )
    result = await session.execute(statement)
    return [RoomWithRole(room=room, role=role) for room, role in result.all()]


async def get_room_for_user(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
) -> RoomWithRole:
    statement = (
        select(Room, RoomMember.role)
        .join(Membership, Membership.workspace_id == Room.workspace_id)
        .outerjoin(
            RoomMember,
            (RoomMember.room_id == Room.id) & (RoomMember.user_id == user.id),
        )
        .where(Room.id == room_id, Membership.user_id == user.id)
    )
    result = await session.execute(statement)
    row = result.one_or_none()
    if row is None:
        raise RoomNotFoundError
    room, role = row
    return RoomWithRole(room=room, role=role)


async def list_room_members(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
) -> list[RoomMemberWithUser]:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is None:
        raise RoomNotFoundError

    result = await session.execute(
        select(RoomMember, User)
        .join(User, User.id == RoomMember.user_id)
        .where(RoomMember.room_id == room_id)
        .order_by(User.display_name, User.email)
    )
    return [
        RoomMemberWithUser(room_member=room_member, user=member_user)
        for room_member, member_user in result.all()
    ]


async def add_room_member(
    session: AsyncSession,
    *,
    actor: User,
    room_id: UUID,
    user_id: UUID,
    role: str,
) -> RoomMemberWithUser:
    room_with_role = await get_room_for_user(session, user=actor, room_id=room_id)
    await require_room_manager(
        session, user=actor, room=room_with_role.room, role=room_with_role.role
    )

    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFoundError

    result = await session.execute(
        select(Membership).where(
            Membership.workspace_id == room_with_role.room.workspace_id,
            Membership.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise WorkspaceMembershipRequiredError

    result = await session.execute(
        select(RoomMember).where(
            RoomMember.room_id == room_id,
            RoomMember.user_id == user.id,
        )
    )
    room_member = result.scalar_one_or_none()
    if room_member is None:
        room_member = RoomMember(room_id=room_id, user_id=user.id, role=role)
        session.add(room_member)
    else:
        room_member.role = role
    await session.flush()
    await record_audit_log(
        session,
        workspace_id=room_with_role.room.workspace_id,
        actor_id=actor.id,
        action="room.member_upserted",
        target_type="room_member",
        target_id=room_member.id,
        details={
            "room_id": str(room_id),
            "user_id": str(user.id),
            "email": user.email,
            "role": role,
        },
    )

    await session.commit()
    await session.refresh(room_member)
    return RoomMemberWithUser(room_member=room_member, user=user)


async def update_room_member_role(
    session: AsyncSession,
    *,
    actor: User,
    room_id: UUID,
    user_id: UUID,
    role: str,
) -> RoomMemberWithUser:
    room_with_role = await get_room_for_user(session, user=actor, room_id=room_id)
    await require_room_manager(
        session, user=actor, room=room_with_role.room, role=room_with_role.role
    )
    member_with_user = await get_room_member_with_user(
        session,
        room_id=room_id,
        user_id=user_id,
    )
    if member_with_user.room_member.role == RoomRole.OWNER.value and role != RoomRole.OWNER.value:
        await ensure_room_has_another_owner(session, room_id=room_id, user_id=user_id)

    member_with_user.room_member.role = role
    await session.flush()
    await record_audit_log(
        session,
        workspace_id=room_with_role.room.workspace_id,
        actor_id=actor.id,
        action="room.member_role_updated",
        target_type="room_member",
        target_id=member_with_user.room_member.id,
        details={
            "room_id": str(room_id),
            "user_id": str(user_id),
            "email": member_with_user.user.email,
            "role": role,
        },
    )
    await session.commit()
    await session.refresh(member_with_user.room_member)
    return member_with_user


async def remove_room_member(
    session: AsyncSession,
    *,
    actor: User,
    room_id: UUID,
    user_id: UUID,
) -> None:
    room_with_role = await get_room_for_user(session, user=actor, room_id=room_id)
    await require_room_manager(
        session, user=actor, room=room_with_role.room, role=room_with_role.role
    )
    member_with_user = await get_room_member_with_user(
        session,
        room_id=room_id,
        user_id=user_id,
    )
    if member_with_user.room_member.role == RoomRole.OWNER.value:
        await ensure_room_has_another_owner(session, room_id=room_id, user_id=user_id)

    await session.delete(member_with_user.room_member)
    await record_audit_log(
        session,
        workspace_id=room_with_role.room.workspace_id,
        actor_id=actor.id,
        action="room.member_removed",
        target_type="room_member",
        target_id=member_with_user.room_member.id,
        details={
            "room_id": str(room_id),
            "user_id": str(user_id),
            "email": member_with_user.user.email,
        },
    )
    await session.commit()


async def join_room(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
) -> RoomWithRole:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is not None:
        return room_with_role

    session.add(
        RoomMember(
            room_id=room_with_role.room.id,
            user_id=user.id,
            role=RoomRole.MEMBER.value,
        )
    )
    await session.commit()
    await session.refresh(room_with_role.room)
    return RoomWithRole(room=room_with_role.room, role=RoomRole.MEMBER.value)


async def leave_room(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
) -> RoomWithRole:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is None:
        return room_with_role

    await session.execute(
        delete(RoomMember).where(RoomMember.room_id == room_id, RoomMember.user_id == user.id)
    )
    await session.commit()
    await session.refresh(room_with_role.room)
    return RoomWithRole(room=room_with_role.room, role=None)


async def require_workspace_owner(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
) -> None:
    workspace = await get_workspace_for_user(session, user=user, workspace_id=workspace_id)
    if workspace.role != WorkspaceRole.OWNER.value:
        raise WorkspaceOwnerRequiredError


async def get_workspace_membership_with_user(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> MembershipWithUser:
    result = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == workspace_id, Membership.user_id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise WorkspaceMemberNotFoundError
    membership, user = row
    return MembershipWithUser(membership=membership, user=user)


async def ensure_workspace_has_another_owner(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> None:
    result = await session.execute(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.workspace_id == workspace_id,
            Membership.role == WorkspaceRole.OWNER.value,
            Membership.user_id != user_id,
        )
    )
    if int(result.scalar_one()) == 0:
        raise WorkspaceLastOwnerError


async def get_room_member_with_user(
    session: AsyncSession,
    *,
    room_id: UUID,
    user_id: UUID,
) -> RoomMemberWithUser:
    result = await session.execute(
        select(RoomMember, User)
        .join(User, User.id == RoomMember.user_id)
        .where(RoomMember.room_id == room_id, RoomMember.user_id == user_id)
    )
    row = result.one_or_none()
    if row is None:
        raise RoomMemberNotFoundError
    room_member, user = row
    return RoomMemberWithUser(room_member=room_member, user=user)


async def ensure_room_has_another_owner(
    session: AsyncSession,
    *,
    room_id: UUID,
    user_id: UUID,
) -> None:
    result = await session.execute(
        select(func.count())
        .select_from(RoomMember)
        .where(
            RoomMember.room_id == room_id,
            RoomMember.role == RoomRole.OWNER.value,
            RoomMember.user_id != user_id,
        )
    )
    if int(result.scalar_one()) == 0:
        raise RoomLastOwnerError


async def require_room_manager(
    session: AsyncSession,
    *,
    user: User,
    room: Room,
    role: str | None,
) -> None:
    if role == RoomRole.OWNER.value:
        return

    workspace = await get_workspace_for_user(session, user=user, workspace_id=room.workspace_id)
    if workspace.role != WorkspaceRole.OWNER.value:
        raise RoomOwnerRequiredError


def normalize_slug(value: str) -> str:
    slug = _slug_pattern.sub("-", value.strip().lower()).strip("-")
    if not slug:
        return "untitled"
    return slug[:80].rstrip("-") or "untitled"
