from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import User


class EmailAlreadyRegisteredError(Exception):
    """Raised when a user tries to register an email that already exists."""


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    statement = select(User).where(User.email == normalize_email(email))
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str,
    first_user_system_admin: bool = True,
) -> User:
    user_count_result = await session.execute(select(func.count()).select_from(User))
    is_first_user = user_count_result.scalar_one() == 0
    user = User(
        email=normalize_email(email),
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        is_system_admin=first_user_system_admin and is_first_user,
    )
    session.add(user)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise EmailAlreadyRegisteredError from exc

    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
) -> User | None:
    user = await get_user_by_email(session, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def normalize_email(email: str) -> str:
    return email.strip().lower()
