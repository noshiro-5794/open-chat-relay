from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, Message, Notification, RoomMember, User


class NotificationNotFoundError(Exception):
    """Raised when a notification is not visible to the current user."""


async def create_message_notifications(
    session: AsyncSession,
    *,
    message: Message,
    event: Event,
    sender: User | None,
) -> list[Notification]:
    result = await session.execute(
        select(RoomMember.user_id).where(RoomMember.room_id == message.room_id)
    )
    recipient_ids = [user_id for user_id in result.scalars().all() if user_id != message.sender_id]
    if not recipient_ids:
        return []

    sender_name = sender.display_name if sender is not None else "Bot"
    notifications = [
        Notification(
            user_id=recipient_id,
            workspace_id=message.workspace_id,
            room_id=message.room_id,
            event_id=event.id,
            notification_type="message.created",
            title=f"New message from {sender_name}",
            body=message.content[:1000],
            payload={
                "message_id": str(message.id),
                "room_id": str(message.room_id),
                "sender_type": message.sender_type,
                "sender_id": str(message.sender_id) if message.sender_id else None,
                "sender_bot_id": str(message.sender_bot_id) if message.sender_bot_id else None,
            },
        )
        for recipient_id in recipient_ids
    ]
    session.add_all(notifications)
    return notifications


async def list_user_notifications(
    session: AsyncSession,
    *,
    user_id: UUID,
    limit: int,
    unread_only: bool,
) -> list[Notification]:
    statement = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        statement = statement.where(Notification.read_at.is_(None))
    statement = statement.order_by(
        Notification.created_at.desc(),
        Notification.id.desc(),
    ).limit(limit)
    result = await session.execute(statement)
    return list(result.scalars().all())


async def unread_notification_count(session: AsyncSession, *, user_id: UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
    )
    return result.scalar_one()


async def mark_notification_read(
    session: AsyncSession,
    *,
    user_id: UUID,
    notification_id: UUID,
) -> Notification:
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        raise NotificationNotFoundError
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(notification)
    return notification


async def mark_all_notifications_read(session: AsyncSession, *, user_id: UUID) -> int:
    notifications = await list_user_notifications(
        session,
        user_id=user_id,
        limit=500,
        unread_only=True,
    )
    now = datetime.now(UTC)
    for notification in notifications:
        notification.read_at = now
    if notifications:
        await session.commit()
    return len(notifications)
