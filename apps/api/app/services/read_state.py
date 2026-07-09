from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, MessageSenderType, RoomReadState, User
from app.realtime.policies import DURABLE_DELIVERY
from app.services.message import (
    RoomMembershipRequiredError,
    next_room_event_seq,
    next_workspace_event_seq,
)
from app.services.outbox import enqueue_event_outbox
from app.services.workspace import get_room_for_user


class ReadStateAheadOfRoomError(Exception):
    """Raised when a read state points beyond the current room event stream."""


@dataclass(frozen=True)
class ReadStateWithEvent:
    read_state: RoomReadState
    event: Event | None


async def update_room_read_state(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    last_read_event_seq: int,
) -> ReadStateWithEvent:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is None:
        raise RoomMembershipRequiredError

    latest_seq = await latest_room_event_seq(session, room_id=room_with_role.room.id)
    if last_read_event_seq > latest_seq:
        raise ReadStateAheadOfRoomError

    read_state = await get_or_create_read_state(
        session,
        user=user,
        workspace_id=room_with_role.room.workspace_id,
        room_id=room_with_role.room.id,
    )
    if last_read_event_seq <= read_state.last_read_event_seq:
        await session.commit()
        await session.refresh(read_state)
        return ReadStateWithEvent(read_state=read_state, event=None)

    read_state.last_read_event_seq = last_read_event_seq
    await session.flush()

    room_event_seq = await next_room_event_seq(session, room_id=room_with_role.room.id)
    workspace_event_seq = await next_workspace_event_seq(
        session,
        workspace_id=room_with_role.room.workspace_id,
    )
    event = Event(
        workspace_id=room_with_role.room.workspace_id,
        room_id=room_with_role.room.id,
        actor_id=user.id,
        actor_type=MessageSenderType.USER.value,
        actor_bot_id=None,
        event_type="room.read_state_updated",
        aggregate_type="room_read_state",
        aggregate_id=read_state.id,
        room_event_seq=room_event_seq,
        workspace_event_seq=workspace_event_seq,
        lane=DURABLE_DELIVERY.lane.value,
        reliability=DURABLE_DELIVERY.reliability.value,
        ordering=DURABLE_DELIVERY.ordering.value,
        priority=DURABLE_DELIVERY.priority.value,
        ttl_ms=DURABLE_DELIVERY.ttl_ms,
        payload={
            "room_id": str(room_with_role.room.id),
            "user_id": str(user.id),
            "last_read_event_seq": read_state.last_read_event_seq,
        },
    )
    session.add(event)
    await session.flush()
    await enqueue_event_outbox(session, event=event)
    await session.commit()
    await session.refresh(read_state)
    await session.refresh(event)
    return ReadStateWithEvent(read_state=read_state, event=event)


async def get_room_read_state(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
) -> RoomReadState:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is None:
        raise RoomMembershipRequiredError

    return await get_or_create_read_state(
        session,
        user=user,
        workspace_id=room_with_role.room.workspace_id,
        room_id=room_with_role.room.id,
    )


async def list_room_read_states(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
) -> list[RoomReadState]:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is None:
        raise RoomMembershipRequiredError

    result = await session.execute(
        select(RoomReadState)
        .where(RoomReadState.room_id == room_with_role.room.id)
        .order_by(RoomReadState.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_or_create_read_state(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: UUID,
    room_id: UUID,
) -> RoomReadState:
    result = await session.execute(
        select(RoomReadState).where(
            RoomReadState.room_id == room_id,
            RoomReadState.user_id == user.id,
        )
    )
    read_state = result.scalar_one_or_none()
    if read_state is not None:
        return read_state

    read_state = RoomReadState(
        workspace_id=workspace_id,
        room_id=room_id,
        user_id=user.id,
        last_read_event_seq=0,
    )
    session.add(read_state)
    await session.flush()
    return read_state


async def latest_room_event_seq(session: AsyncSession, *, room_id: UUID) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(Event.room_event_seq), 0)).where(Event.room_id == room_id)
    )
    return int(result.scalar_one())
