from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserContact
from app.services.auth import get_user_by_email


class FriendNotFoundError(Exception):
    """Raised when a friend relationship cannot be found."""


class SelfFriendError(Exception):
    """Raised when a user tries to add themselves as a friend."""


class UserNotFoundError(Exception):
    """Raised when a requested user cannot be found."""


@dataclass(frozen=True)
class FriendWithUser:
    contact: UserContact
    user: User


async def list_friends(session: AsyncSession, *, user: User) -> list[FriendWithUser]:
    result = await session.execute(
        select(UserContact, User)
        .join(User, User.id == UserContact.contact_user_id)
        .where(UserContact.owner_user_id == user.id, User.is_active.is_(True))
        .order_by(User.display_name, User.email)
    )
    return [FriendWithUser(contact=contact, user=friend) for contact, friend in result.all()]


async def add_friend_by_email(
    session: AsyncSession,
    *,
    user: User,
    email: str,
) -> FriendWithUser:
    friend = await get_user_by_email(session, email)
    if friend is None or not friend.is_active:
        raise UserNotFoundError
    if friend.id == user.id:
        raise SelfFriendError

    contact = await ensure_contact(session, owner_user_id=user.id, contact_user_id=friend.id)
    await ensure_contact(session, owner_user_id=friend.id, contact_user_id=user.id)
    await session.commit()
    await session.refresh(contact)
    return FriendWithUser(contact=contact, user=friend)


async def remove_friend(session: AsyncSession, *, user: User, friend_user_id: UUID) -> None:
    result = await session.execute(
        select(UserContact).where(
            UserContact.owner_user_id == user.id,
            UserContact.contact_user_id == friend_user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise FriendNotFoundError

    await session.execute(
        delete(UserContact).where(
            (UserContact.owner_user_id == user.id)
            & (UserContact.contact_user_id == friend_user_id)
        )
    )
    await session.execute(
        delete(UserContact).where(
            (UserContact.owner_user_id == friend_user_id)
            & (UserContact.contact_user_id == user.id)
        )
    )
    await session.commit()


async def ensure_mutual_contacts(
    session: AsyncSession,
    *,
    first_user_id: UUID,
    second_user_id: UUID,
) -> None:
    if first_user_id == second_user_id:
        return
    await ensure_contact(session, owner_user_id=first_user_id, contact_user_id=second_user_id)
    await ensure_contact(session, owner_user_id=second_user_id, contact_user_id=first_user_id)


async def ensure_contact(
    session: AsyncSession,
    *,
    owner_user_id: UUID,
    contact_user_id: UUID,
) -> UserContact:
    result = await session.execute(
        select(UserContact).where(
            UserContact.owner_user_id == owner_user_id,
            UserContact.contact_user_id == contact_user_id,
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        contact = UserContact(owner_user_id=owner_user_id, contact_user_id=contact_user_id)
        session.add(contact)
        await session.flush()
    return contact
