from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbSessionDep, SettingsDep
from app.core.config import Settings
from app.core.security import (
    TokenType,
    TokenValidationError,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.schemas.auth import (
    AuthSessionResponse,
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from app.services.auth import (
    EmailAlreadyRegisteredError,
    authenticate_user,
    get_user_by_id,
    register_user,
)
from app.services.auth_session import (
    AuthSessionNotFoundError,
    create_auth_session,
    get_active_auth_session_for_refresh_token,
    list_active_auth_sessions,
    revoke_auth_session,
    revoke_refresh_token_session,
    revoke_user_auth_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenPairResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: DbSessionDep,
    settings: SettingsDep,
) -> TokenPairResponse:
    try:
        user = await register_user(
            session,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            first_user_system_admin=settings.first_user_system_admin,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered.",
        ) from exc

    return await create_token_pair(
        session=session,
        user=UserResponse.model_validate(user),
        settings=settings,
    )


@router.post("/login", response_model=TokenPairResponse)
async def login(
    payload: LoginRequest,
    session: DbSessionDep,
    settings: SettingsDep,
) -> TokenPairResponse:
    user = await authenticate_user(session, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return await create_token_pair(
        session=session,
        user=UserResponse.model_validate(user),
        settings=settings,
    )


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(
    payload: RefreshRequest,
    session: DbSessionDep,
    settings: SettingsDep,
) -> TokenPairResponse:
    try:
        user_id = decode_token(
            payload.refresh_token,
            expected_type=TokenType.REFRESH,
            settings=settings,
        )
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    auth_session = await get_active_auth_session_for_refresh_token(
        session,
        refresh_token=payload.refresh_token,
        settings=settings,
    )
    if auth_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await revoke_auth_session(auth_session)
    return await create_token_pair(
        session=session,
        user=UserResponse.model_validate(user),
        settings=settings,
    )


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    current_user: CurrentUserDep,
    session: DbSessionDep,
    settings: SettingsDep,
    payload: LogoutRequest | None = None,
) -> LogoutResponse:
    if payload is not None and payload.refresh_token is not None:
        with suppress(TokenValidationError):
            await revoke_refresh_token_session(
                session,
                refresh_token=payload.refresh_token,
                settings=settings,
            )
    _ = current_user
    return LogoutResponse(status="ok")


@router.get("/sessions", response_model=list[AuthSessionResponse])
async def list_auth_sessions(
    current_user: CurrentUserDep,
    session: DbSessionDep,
) -> list[AuthSessionResponse]:
    auth_sessions = await list_active_auth_sessions(session, user_id=current_user.id)
    return [AuthSessionResponse.model_validate(auth_session) for auth_session in auth_sessions]


@router.delete("/sessions/{auth_session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_auth_session_endpoint(
    auth_session_id: UUID,
    current_user: CurrentUserDep,
    session: DbSessionDep,
) -> None:
    try:
        await revoke_user_auth_session(
            session,
            user_id=current_user.id,
            auth_session_id=auth_session_id,
        )
    except AuthSessionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auth session not found.",
        ) from exc


async def create_token_pair(
    *,
    session,
    user: UserResponse,
    settings: Settings,
) -> TokenPairResponse:
    refresh_token = create_refresh_token(subject=user.id, settings=settings)
    await create_auth_session(session, refresh_token=refresh_token, settings=settings)
    await session.commit()
    return TokenPairResponse(
        access_token=create_access_token(subject=user.id, settings=settings),
        refresh_token=refresh_token,
        user=user,
    )
