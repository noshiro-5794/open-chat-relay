from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from app.core.config import Settings, get_settings
from app.core.security import TokenType, TokenValidationError, decode_token
from app.db.session import get_db_session
from app.models import User
from app.realtime.presence_store import PresenceStore, create_presence_store
from app.realtime.signal_bus import RealtimeSignalBus, create_realtime_signal_bus
from app.realtime.typing_store import TypingStore, create_typing_store
from app.services.auth import get_user_by_id

DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]

bearer_scheme = HTTPBearer(auto_error=False)
BearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def get_connection_settings(connection: HTTPConnection) -> Settings:
    return getattr(connection.app.state, "settings", get_settings())


SettingsDep = Annotated[Settings, Depends(get_connection_settings)]


def get_presence_store(connection: HTTPConnection) -> PresenceStore:
    settings = get_connection_settings(connection)
    return getattr(connection.app.state, "presence_store", create_presence_store(settings))


PresenceStoreDep = Annotated[PresenceStore, Depends(get_presence_store)]


def get_typing_store(connection: HTTPConnection) -> TypingStore:
    settings = get_connection_settings(connection)
    return getattr(connection.app.state, "typing_store", create_typing_store(settings))


TypingStoreDep = Annotated[TypingStore, Depends(get_typing_store)]


def get_realtime_signal_bus(connection: HTTPConnection) -> RealtimeSignalBus:
    settings = get_connection_settings(connection)
    return getattr(
        connection.app.state,
        "realtime_signal_bus",
        create_realtime_signal_bus(settings),
    )


RealtimeSignalBusDep = Annotated[RealtimeSignalBus, Depends(get_realtime_signal_bus)]


async def get_current_user(
    credentials: BearerDep,
    session: DbSessionDep,
    settings: SettingsDep,
) -> User:
    if credentials is None:
        raise_unauthorized()

    user = await get_user_from_access_token(
        token=credentials.credentials,
        session=session,
        settings=settings,
    )
    if user is None:
        raise_unauthorized()

    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_current_system_admin(current_user: CurrentUserDep) -> User:
    if not current_user.is_system_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System administrator privileges are required.",
        )
    return current_user


SystemAdminDep = Annotated[User, Depends(get_current_system_admin)]


async def get_user_from_access_token(
    *,
    token: str,
    session: AsyncSession,
    settings: Settings,
) -> User | None:
    try:
        user_id = decode_token(token, expected_type=TokenType.ACCESS, settings=settings)
    except TokenValidationError:
        return None

    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        return None
    return user


def raise_unauthorized() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
