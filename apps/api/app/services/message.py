from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Attachment,
    AttachmentStatus,
    Bot,
    Event,
    Message,
    MessageSenderType,
    MessageType,
    Notification,
    Room,
    User,
)
from app.realtime.policies import DURABLE_DELIVERY
from app.services.notification import create_message_notifications
from app.services.outbox import enqueue_event_outbox
from app.services.workspace import RoomNotFoundError, get_room_for_user


class RoomMembershipRequiredError(Exception):
    """Raised when the user can see a room but has not joined it."""


class AttachmentNotFoundError(Exception):
    """Raised when an attachment cannot be attached to a message."""


class MessageNotFoundError(Exception):
    """Raised when a message does not exist or is not visible to the user."""


class MessagePermissionDeniedError(Exception):
    """Raised when a user cannot mutate a message."""


@dataclass(frozen=True)
class MessageWithEvent:
    message: Message
    event: Event
    attachments: list[Attachment]
    notifications: list[Notification]


@dataclass(frozen=True)
class MessagePage:
    messages: list[Message]
    next_before_message_id: UUID | None
    has_more: bool


async def create_message(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    content: str,
    attachment_ids: list[UUID] | None = None,
    reply_to_id: UUID | None = None,
) -> MessageWithEvent:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is None:
        raise RoomMembershipRequiredError

    attachments = await get_attachable_attachments(
        session,
        user=user,
        room_id=room_with_role.room.id,
        attachment_ids=attachment_ids or [],
    )
    reply_to = await get_reply_target(
        session, room_id=room_with_role.room.id, reply_to_id=reply_to_id
    )
    message = Message(
        workspace_id=room_with_role.room.workspace_id,
        room_id=room_with_role.room.id,
        sender_type=MessageSenderType.USER.value,
        sender_id=user.id,
        sender_bot_id=None,
        message_type=MessageType.TEXT.value,
        content=content.strip(),
        message_metadata={},
        reply_to_id=reply_to.id if reply_to is not None else None,
    )
    session.add(message)
    await session.flush()

    for attachment in attachments:
        attachment.message_id = message.id
        attachment.status = AttachmentStatus.ATTACHED.value

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
        event_type="message.created",
        aggregate_type="message",
        aggregate_id=message.id,
        room_event_seq=room_event_seq,
        workspace_event_seq=workspace_event_seq,
        lane=DURABLE_DELIVERY.lane.value,
        reliability=DURABLE_DELIVERY.reliability.value,
        ordering=DURABLE_DELIVERY.ordering.value,
        priority=DURABLE_DELIVERY.priority.value,
        ttl_ms=DURABLE_DELIVERY.ttl_ms,
        payload={
            "message_id": str(message.id),
            "room_id": str(message.room_id),
            "sender_id": str(message.sender_id),
            "sender_type": message.sender_type,
            "sender_bot_id": None,
            "content": message.content,
            "message_type": message.message_type,
            "reply_to_id": str(message.reply_to_id) if message.reply_to_id else None,
            "attachments": [attachment_payload(attachment) for attachment in attachments],
        },
    )
    session.add(event)
    await session.flush()
    await enqueue_event_outbox(session, event=event)
    notifications = await create_message_notifications(
        session,
        message=message,
        event=event,
        sender=user,
    )

    await session.commit()
    await session.refresh(message)
    await session.refresh(event)
    for attachment in attachments:
        await session.refresh(attachment)
    for notification in notifications:
        await session.refresh(notification)
    return MessageWithEvent(
        message=message,
        event=event,
        attachments=attachments,
        notifications=notifications,
    )


async def create_bot_message(
    session: AsyncSession,
    *,
    bot: Bot,
    room_id: UUID,
    content: str,
    attachment_ids: list[UUID] | None = None,
    metadata: dict[str, Any] | None = None,
    reply_to_id: UUID | None = None,
) -> MessageWithEvent:
    if attachment_ids:
        raise AttachmentNotFoundError

    room = await get_room_for_workspace_app(session, bot=bot, room_id=room_id)
    reply_to = await get_reply_target(session, room_id=room.id, reply_to_id=reply_to_id)
    message = Message(
        workspace_id=room.workspace_id,
        room_id=room.id,
        sender_type=MessageSenderType.BOT.value,
        sender_id=None,
        sender_bot_id=bot.id,
        message_type=MessageType.TEXT.value,
        content=content.strip(),
        message_metadata=metadata or {},
        reply_to_id=reply_to.id if reply_to is not None else None,
    )
    session.add(message)
    await session.flush()

    room_event_seq = await next_room_event_seq(session, room_id=room.id)
    workspace_event_seq = await next_workspace_event_seq(
        session,
        workspace_id=room.workspace_id,
    )
    event = Event(
        workspace_id=room.workspace_id,
        room_id=room.id,
        actor_id=None,
        actor_type=MessageSenderType.BOT.value,
        actor_bot_id=bot.id,
        event_type="message.created",
        aggregate_type="message",
        aggregate_id=message.id,
        room_event_seq=room_event_seq,
        workspace_event_seq=workspace_event_seq,
        lane=DURABLE_DELIVERY.lane.value,
        reliability=DURABLE_DELIVERY.reliability.value,
        ordering=DURABLE_DELIVERY.ordering.value,
        priority=DURABLE_DELIVERY.priority.value,
        ttl_ms=DURABLE_DELIVERY.ttl_ms,
        payload={
            "message_id": str(message.id),
            "room_id": str(message.room_id),
            "sender_id": None,
            "sender_type": message.sender_type,
            "sender_bot_id": str(bot.id),
            "app_id": str(bot.app_id),
            "content": message.content,
            "message_type": message.message_type,
            "reply_to_id": str(message.reply_to_id) if message.reply_to_id else None,
            "metadata": message.message_metadata,
            "attachments": [],
        },
    )
    session.add(event)
    await session.flush()
    await enqueue_event_outbox(session, event=event)
    notifications = await create_message_notifications(
        session,
        message=message,
        event=event,
        sender=None,
    )

    await session.commit()
    await session.refresh(message)
    await session.refresh(event)
    for notification in notifications:
        await session.refresh(notification)
    return MessageWithEvent(
        message=message,
        event=event,
        attachments=[],
        notifications=notifications,
    )


async def update_message(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    message_id: UUID,
    content: str,
) -> MessageWithEvent:
    await ensure_room_member(session, user=user, room_id=room_id)
    message = await get_mutable_message(
        session,
        user=user,
        room_id=room_id,
        message_id=message_id,
    )
    message.content = content.strip()

    event = await create_message_event(
        session,
        message=message,
        actor_id=user.id,
        actor_type=MessageSenderType.USER.value,
        actor_bot_id=None,
        event_type="message.updated",
        payload={
            "message_id": str(message.id),
            "room_id": str(message.room_id),
            "sender_id": str(message.sender_id),
            "sender_type": message.sender_type,
            "sender_bot_id": str(message.sender_bot_id) if message.sender_bot_id else None,
            "content": message.content,
            "message_type": message.message_type,
            "reply_to_id": str(message.reply_to_id) if message.reply_to_id else None,
        },
    )

    await session.commit()
    await session.refresh(message)
    await session.refresh(event)
    attachments = await list_attachments_for_message(session, message_id=message.id)
    return MessageWithEvent(
        message=message,
        event=event,
        attachments=attachments,
        notifications=[],
    )


async def delete_message(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    message_id: UUID,
) -> MessageWithEvent:
    await ensure_room_member(session, user=user, room_id=room_id)
    message = await get_mutable_message(
        session,
        user=user,
        room_id=room_id,
        message_id=message_id,
    )
    message.deleted_at = datetime.now(UTC)

    event = await create_message_event(
        session,
        message=message,
        actor_id=user.id,
        actor_type=MessageSenderType.USER.value,
        actor_bot_id=None,
        event_type="message.deleted",
        payload={
            "message_id": str(message.id),
            "room_id": str(message.room_id),
            "sender_id": str(message.sender_id),
            "sender_type": message.sender_type,
            "sender_bot_id": str(message.sender_bot_id) if message.sender_bot_id else None,
            "reply_to_id": str(message.reply_to_id) if message.reply_to_id else None,
            "deleted_at": message.deleted_at.isoformat(),
        },
    )

    await session.commit()
    await session.refresh(message)
    await session.refresh(event)
    attachments = await list_attachments_for_message(session, message_id=message.id)
    return MessageWithEvent(
        message=message,
        event=event,
        attachments=attachments,
        notifications=[],
    )


async def list_messages(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    limit: int,
) -> list[Message]:
    await ensure_room_member(session, user=user, room_id=room_id)

    statement = (
        select(Message)
        .where(Message.room_id == room_id, Message.deleted_at.is_(None))
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(reversed(result.scalars().all()))


async def list_messages_page(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    limit: int,
    before_message_id: UUID | None = None,
) -> MessagePage:
    await ensure_room_member(session, user=user, room_id=room_id)

    cursor_message: Message | None = None
    if before_message_id is not None:
        cursor_message = await get_visible_message(
            session,
            room_id=room_id,
            message_id=before_message_id,
        )

    statement = select(Message).where(Message.room_id == room_id, Message.deleted_at.is_(None))
    if cursor_message is not None:
        statement = statement.where(
            (Message.created_at < cursor_message.created_at)
            | (
                (Message.created_at == cursor_message.created_at)
                & (Message.id < cursor_message.id)
            )
        )

    statement = statement.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)
    result = await session.execute(statement)
    newest_first = list(result.scalars().all())
    has_more = len(newest_first) > limit
    page_messages = newest_first[:limit]
    messages = list(reversed(page_messages))
    return MessagePage(
        messages=messages,
        next_before_message_id=messages[0].id if has_more and messages else None,
        has_more=has_more,
    )


async def search_messages(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    query: str,
    limit: int,
) -> list[Message]:
    await ensure_room_member(session, user=user, room_id=room_id)

    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    statement = (
        select(Message)
        .where(
            Message.room_id == room_id,
            Message.deleted_at.is_(None),
            func.lower(Message.content).contains(normalized_query),
        )
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def list_message_replies(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    message_id: UUID,
    limit: int,
) -> list[Message]:
    await ensure_room_member(session, user=user, room_id=room_id)
    await get_visible_message(session, room_id=room_id, message_id=message_id)

    statement = (
        select(Message)
        .where(
            Message.room_id == room_id,
            Message.reply_to_id == message_id,
            Message.deleted_at.is_(None),
        )
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def list_room_events(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    after_seq: int | None,
    limit: int,
) -> list[Event]:
    await ensure_room_member(session, user=user, room_id=room_id)

    statement: Select[tuple[Event]] = (
        select(Event).where(Event.room_id == room_id).order_by(Event.room_event_seq).limit(limit)
    )
    if after_seq is not None:
        statement = statement.where(Event.room_event_seq > after_seq)

    result = await session.execute(statement)
    return list(result.scalars().all())


async def ensure_room_member(session: AsyncSession, *, user: User, room_id: UUID) -> None:
    room_with_role = await get_room_for_user(session, user=user, room_id=room_id)
    if room_with_role.role is None:
        raise RoomMembershipRequiredError


async def get_room_for_workspace_app(session: AsyncSession, *, bot: Bot, room_id: UUID) -> Room:
    room = await session.get(Room, room_id)
    if room is None or room.workspace_id != bot.workspace_id:
        raise RoomNotFoundError
    return room


async def get_mutable_message(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    message_id: UUID,
) -> Message:
    message = await session.get(Message, message_id)
    if message is None or message.room_id != room_id or message.deleted_at is not None:
        raise MessageNotFoundError
    if message.sender_id != user.id:
        raise MessagePermissionDeniedError
    return message


async def get_visible_message(
    session: AsyncSession,
    *,
    room_id: UUID,
    message_id: UUID,
) -> Message:
    message = await session.get(Message, message_id)
    if message is None or message.room_id != room_id or message.deleted_at is not None:
        raise MessageNotFoundError
    return message


async def get_reply_target(
    session: AsyncSession,
    *,
    room_id: UUID,
    reply_to_id: UUID | None,
) -> Message | None:
    if reply_to_id is None:
        return None
    return await get_visible_message(session, room_id=room_id, message_id=reply_to_id)


async def get_attachable_attachments(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    attachment_ids: list[UUID],
) -> list[Attachment]:
    if not attachment_ids:
        return []

    statement = select(Attachment).where(
        Attachment.id.in_(attachment_ids),
        Attachment.room_id == room_id,
        Attachment.uploader_id == user.id,
        Attachment.message_id.is_(None),
        Attachment.status == AttachmentStatus.UPLOADED.value,
    )
    result = await session.execute(statement)
    attachments = list(result.scalars().all())
    if len(attachments) != len(set(attachment_ids)):
        raise AttachmentNotFoundError
    return attachments


async def list_attachments_for_messages(
    session: AsyncSession,
    *,
    message_ids: list[UUID],
) -> dict[UUID, list[Attachment]]:
    if not message_ids:
        return {}

    statement = (
        select(Attachment)
        .where(Attachment.message_id.in_(message_ids))
        .order_by(Attachment.created_at)
    )
    result = await session.execute(statement)
    attachments_by_message: dict[UUID, list[Attachment]] = {}
    for attachment in result.scalars().all():
        if attachment.message_id is None:
            continue
        attachments_by_message.setdefault(attachment.message_id, []).append(attachment)
    return attachments_by_message


async def list_attachments_for_message(
    session: AsyncSession,
    *,
    message_id: UUID,
) -> list[Attachment]:
    return (await list_attachments_for_messages(session, message_ids=[message_id])).get(
        message_id,
        [],
    )


async def next_room_event_seq(session: AsyncSession, *, room_id: UUID) -> int:
    statement = select(func.coalesce(func.max(Event.room_event_seq), 0)).where(
        Event.room_id == room_id
    )
    result = await session.execute(statement)
    return int(result.scalar_one()) + 1


async def next_workspace_event_seq(session: AsyncSession, *, workspace_id: UUID) -> int:
    statement = select(func.coalesce(func.max(Event.workspace_event_seq), 0)).where(
        Event.workspace_id == workspace_id
    )
    result = await session.execute(statement)
    return int(result.scalar_one()) + 1


async def create_message_event(
    session: AsyncSession,
    *,
    message: Message,
    actor_id: UUID,
    actor_type: str = MessageSenderType.USER.value,
    actor_bot_id: UUID | None = None,
    event_type: str,
    payload: dict,
) -> Event:
    room_event_seq = await next_room_event_seq(session, room_id=message.room_id)
    workspace_event_seq = await next_workspace_event_seq(
        session,
        workspace_id=message.workspace_id,
    )
    event = Event(
        workspace_id=message.workspace_id,
        room_id=message.room_id,
        actor_id=actor_id,
        actor_type=actor_type,
        actor_bot_id=actor_bot_id,
        event_type=event_type,
        aggregate_type="message",
        aggregate_id=message.id,
        room_event_seq=room_event_seq,
        workspace_event_seq=workspace_event_seq,
        lane=DURABLE_DELIVERY.lane.value,
        reliability=DURABLE_DELIVERY.reliability.value,
        ordering=DURABLE_DELIVERY.ordering.value,
        priority=DURABLE_DELIVERY.priority.value,
        ttl_ms=DURABLE_DELIVERY.ttl_ms,
        payload=payload,
    )
    session.add(event)
    await session.flush()
    await enqueue_event_outbox(session, event=event)
    return event


def attachment_payload(attachment: Attachment) -> dict:
    return {
        "id": str(attachment.id),
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "storage_key": attachment.storage_key,
        "status": attachment.status,
    }
