import asyncio
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.api.deps import DbSessionDep, SettingsDep, get_user_from_access_token, raise_unauthorized
from app.models import User
from app.realtime.sse import format_sse_event, sse_heartbeat
from app.services.message import RoomMembershipRequiredError, ensure_room_member, list_room_events
from app.services.workspace import RoomNotFoundError

router = APIRouter(prefix="/rooms/{room_id}/events/stream", tags=["events"])

AuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]
TokenQuery = Annotated[str | None, Query()]
LastEventSeqQuery = Annotated[int | None, Query(ge=0)]
OnceQuery = Annotated[bool, Query()]


@router.get("")
async def stream_room_events(
    room_id: UUID,
    request: Request,
    session: DbSessionDep,
    settings: SettingsDep,
    authorization: AuthorizationHeader = None,
    token: TokenQuery = None,
    last_event_seq: LastEventSeqQuery = None,
    once: OnceQuery = False,
) -> StreamingResponse:
    user = await authenticate_stream_user(
        authorization=authorization,
        token=token,
        session=session,
        settings=settings,
    )
    await require_room_member(session=session, user=user, room_id=room_id)

    return StreamingResponse(
        event_generator(
            request=request,
            session=session,
            settings=settings,
            user=user,
            room_id=room_id,
            last_event_seq=last_event_seq,
            once=once,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def authenticate_stream_user(
    *,
    authorization: str | None,
    token: str | None,
    session: DbSessionDep,
    settings: SettingsDep,
) -> User:
    access_token = token or bearer_token_from_header(authorization)
    if access_token is None:
        raise_unauthorized()

    user = await get_user_from_access_token(token=access_token, session=session, settings=settings)
    if user is None:
        raise_unauthorized()
    return user


async def require_room_member(*, session: DbSessionDep, user: User, room_id: UUID) -> None:
    try:
        await ensure_room_member(session, user=user, room_id=room_id)
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before streaming events.",
        ) from exc


async def event_generator(
    *,
    request: Request,
    session: DbSessionDep,
    settings: SettingsDep,
    user: User,
    room_id: UUID,
    last_event_seq: int | None,
    once: bool,
) -> AsyncIterator[str]:
    current_seq = last_event_seq
    while True:
        if await request.is_disconnected():
            return

        events = await list_room_events(
            session,
            user=user,
            room_id=room_id,
            after_seq=current_seq,
            limit=100,
        )
        for event in events:
            current_seq = event.room_event_seq
            yield format_sse_event(event)

        if once:
            return

        if not events:
            yield sse_heartbeat()

        await asyncio.sleep(settings.sse_poll_interval_seconds)


def bearer_token_from_header(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token
