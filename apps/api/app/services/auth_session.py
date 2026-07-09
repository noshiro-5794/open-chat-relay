from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import TokenType, decode_token_claims, hash_token
from app.models import AuthSession


class AuthSessionNotFoundError(Exception):
    """Raised when an auth session cannot be found for the user."""


async def create_auth_session(
    session: AsyncSession,
    *,
    refresh_token: str,
    settings: Settings,
) -> AuthSession:
    claims = decode_token_claims(
        refresh_token,
        expected_type=TokenType.REFRESH,
        settings=settings,
    )
    auth_session = AuthSession(
        user_id=claims.subject,
        refresh_token_jti=claims.token_id or "",
        refresh_token_hash=hash_token(refresh_token),
        expires_at=claims.expires_at,
        revoked_at=None,
        last_used_at=None,
    )
    session.add(auth_session)
    return auth_session


async def get_active_auth_session_for_refresh_token(
    session: AsyncSession,
    *,
    refresh_token: str,
    settings: Settings,
) -> AuthSession | None:
    claims = decode_token_claims(
        refresh_token,
        expected_type=TokenType.REFRESH,
        settings=settings,
    )
    if claims.token_id is None:
        return None

    now = datetime.now(UTC)
    result = await session.execute(
        select(AuthSession).where(
            AuthSession.refresh_token_jti == claims.token_id,
            AuthSession.refresh_token_hash == hash_token(refresh_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )
    auth_session = result.scalar_one_or_none()
    if auth_session is None:
        return None
    auth_session.last_used_at = now
    return auth_session


async def revoke_auth_session(auth_session: AuthSession) -> None:
    auth_session.revoked_at = datetime.now(UTC)


async def list_active_auth_sessions(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> list[AuthSession]:
    now = datetime.now(UTC)
    result = await session.execute(
        select(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .order_by(AuthSession.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_user_auth_session(
    session: AsyncSession,
    *,
    user_id: UUID,
    auth_session_id: UUID,
) -> None:
    result = await session.execute(
        select(AuthSession).where(
            AuthSession.id == auth_session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
    )
    auth_session = result.scalar_one_or_none()
    if auth_session is None:
        raise AuthSessionNotFoundError
    await revoke_auth_session(auth_session)
    await session.commit()


async def revoke_refresh_token_session(
    session: AsyncSession,
    *,
    refresh_token: str,
    settings: Settings,
) -> None:
    auth_session = await get_active_auth_session_for_refresh_token(
        session,
        refresh_token=refresh_token,
        settings=settings,
    )
    if auth_session is None:
        return
    await revoke_auth_session(auth_session)
    await session.commit()
