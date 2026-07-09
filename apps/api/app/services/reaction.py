from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, MessageReaction, User
from app.services.message import (
    MessageNotFoundError,
    create_message_event,
    ensure_room_member,
)


class ReactionAlreadyExistsError(Exception):
    """Raised when a user repeats the same reaction on a message."""


class ReactionNotFoundError(Exception):
    """Raised when a reaction cannot be found for removal."""


@dataclass(frozen=True)
class ReactionWithEvent:
    reaction: MessageReaction


async def add_reaction(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    message_id: UUID,
    emoji: str,
) -> ReactionWithEvent:
    message = await get_visible_message(session, user=user, room_id=room_id, message_id=message_id)
    reaction = MessageReaction(
        workspace_id=message.workspace_id,
        room_id=message.room_id,
        message_id=message.id,
        user_id=user.id,
        emoji=normalize_emoji(emoji),
    )
    session.add(reaction)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ReactionAlreadyExistsError from exc

    await create_message_event(
        session,
        message=message,
        actor_id=user.id,
        event_type="message.reaction_added",
        payload=reaction_payload(reaction),
    )
    await session.commit()
    await session.refresh(reaction)
    return ReactionWithEvent(reaction=reaction)


async def remove_reaction(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    message_id: UUID,
    emoji: str,
) -> ReactionWithEvent:
    message = await get_visible_message(session, user=user, room_id=room_id, message_id=message_id)
    statement = select(MessageReaction).where(
        MessageReaction.room_id == room_id,
        MessageReaction.message_id == message_id,
        MessageReaction.user_id == user.id,
        MessageReaction.emoji == normalize_emoji(emoji),
    )
    result = await session.execute(statement)
    reaction = result.scalar_one_or_none()
    if reaction is None:
        raise ReactionNotFoundError

    await create_message_event(
        session,
        message=message,
        actor_id=user.id,
        event_type="message.reaction_removed",
        payload=reaction_payload(reaction),
    )
    await session.delete(reaction)
    await session.commit()
    return ReactionWithEvent(reaction=reaction)


async def get_visible_message(
    session: AsyncSession,
    *,
    user: User,
    room_id: UUID,
    message_id: UUID,
) -> Message:
    await ensure_room_member(session, user=user, room_id=room_id)
    message = await session.get(Message, message_id)
    if message is None or message.room_id != room_id or message.deleted_at is not None:
        raise MessageNotFoundError
    return message


def reaction_payload(reaction: MessageReaction) -> dict:
    return {
        "reaction_id": str(reaction.id),
        "message_id": str(reaction.message_id),
        "room_id": str(reaction.room_id),
        "user_id": str(reaction.user_id),
        "emoji": reaction.emoji,
    }


def normalize_emoji(emoji: str) -> str:
    return emoji.strip()
