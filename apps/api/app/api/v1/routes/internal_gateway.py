import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from app.api.deps import (
    DbSessionDep,
    PresenceStoreDep,
    RealtimeSignalBusDep,
    SettingsDep,
    TypingStoreDep,
)
from app.core.config import Settings
from app.core.security import TokenType, TokenValidationError, decode_token_claims
from app.models import User
from app.realtime.manager import manager
from app.realtime.notifications import publish_notifications
from app.realtime.protocol import (
    COMMAND_MESSAGE_SEND,
    COMMAND_PRESENCE_UPDATE,
    COMMAND_ROOM_SUBSCRIBE,
    COMMAND_TYPING_UPDATE,
    MessageSendData,
    PresenceUpdateData,
    ProtocolError,
    RoomSubscribeData,
    TypingUpdateData,
    parse_command_data,
    parse_inbound_command,
)
from app.realtime.serializers import (
    ack_payload,
    error_payload,
    event_to_realtime_payload,
    presence_payload,
    typing_payload,
)
from app.schemas.gateway import (
    GatewayAuthenticateRequest,
    GatewayAuthenticateResponse,
    GatewayCommandRequest,
    GatewayCommandResponse,
)
from app.services.auth import get_user_by_id
from app.services.message import (
    MessageNotFoundError,
    RoomMembershipRequiredError,
    create_message,
    ensure_room_member,
    list_room_events,
)
from app.services.workspace import RoomNotFoundError

router = APIRouter(prefix="/internal/gateway", tags=["internal-gateway"])

GatewayTokenHeader = Annotated[
    str | None,
    Header(alias="X-OpenChatRelay-Gateway-Token"),
]


@router.post("/authenticate", response_model=GatewayAuthenticateResponse)
async def authenticate_gateway_session(
    payload: GatewayAuthenticateRequest,
    session: DbSessionDep,
    settings: SettingsDep,
    gateway_token: GatewayTokenHeader = None,
) -> GatewayAuthenticateResponse:
    verify_gateway_token(gateway_token=gateway_token, settings=settings)
    user, claims = await authenticate_gateway_access_token(
        access_token=payload.access_token,
        session=session,
        settings=settings,
    )

    return GatewayAuthenticateResponse(
        user_id=user.id,
        token_expires_at=claims.expires_at,
    )


@router.post("/commands", response_model=GatewayCommandResponse)
async def handle_gateway_command(
    payload: GatewayCommandRequest,
    session: DbSessionDep,
    settings: SettingsDep,
    signal_bus: RealtimeSignalBusDep,
    presence_store: PresenceStoreDep,
    typing_store: TypingStoreDep,
    gateway_token: GatewayTokenHeader = None,
) -> GatewayCommandResponse:
    verify_gateway_token(gateway_token=gateway_token, settings=settings)
    user, _claims = await authenticate_gateway_access_token(
        access_token=payload.access_token,
        session=session,
        settings=settings,
    )

    try:
        command = parse_inbound_command(payload.command)
    except ProtocolError as exc:
        return GatewayCommandResponse(
            frames=[error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)]
        )

    if command.type == COMMAND_ROOM_SUBSCRIBE:
        return await handle_gateway_room_subscribe(command=command, session=session, user=user)

    if command.type == COMMAND_MESSAGE_SEND:
        return await handle_gateway_message_send(
            command=command,
            session=session,
            user=user,
            signal_bus=signal_bus,
        )

    if command.type == COMMAND_PRESENCE_UPDATE:
        return await handle_gateway_presence_update(
            command=command,
            session=session,
            user=user,
            presence_store=presence_store,
            signal_bus=signal_bus,
        )

    if command.type == COMMAND_TYPING_UPDATE:
        return await handle_gateway_typing_update(
            command=command,
            session=session,
            user=user,
            typing_store=typing_store,
            signal_bus=signal_bus,
        )

    return GatewayCommandResponse(
        frames=[
            error_payload(
                request_id=command.request_id,
                code="unknown_command",
                message="Unknown gateway command.",
            )
        ]
    )


async def handle_gateway_room_subscribe(*, command, session: DbSessionDep, user: User):
    try:
        data = parse_command_data(
            command,
            RoomSubscribeData,
            code="invalid_room_id",
            message="Invalid room_id.",
        )
        await ensure_room_member(session, user=user, room_id=data.room_id)
    except RoomNotFoundError:
        return GatewayCommandResponse(
            frames=[
                error_payload(
                    request_id=command.request_id,
                    code="room_not_found",
                    message="Room not found.",
                )
            ]
        )
    except RoomMembershipRequiredError:
        return GatewayCommandResponse(
            frames=[
                error_payload(
                    request_id=command.request_id,
                    code="room_membership_required",
                    message="Join the room before subscribing.",
                )
            ]
        )
    except ProtocolError as exc:
        return GatewayCommandResponse(
            frames=[error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)]
        )

    frames = [ack_payload(request_id=command.request_id)]
    if data.last_event_seq is not None:
        missed_events = await list_room_events(
            session,
            user=user,
            room_id=data.room_id,
            after_seq=data.last_event_seq,
            limit=100,
        )
        frames.extend(event_to_realtime_payload(event) for event in missed_events)
    return GatewayCommandResponse(frames=frames)


async def handle_gateway_message_send(
    *,
    command,
    session: DbSessionDep,
    user: User,
    signal_bus: RealtimeSignalBusDep,
):
    try:
        data = parse_command_data(
            command,
            MessageSendData,
            code="invalid_message",
            message="message.send requires room_id and content.",
        )
        message_with_event = await create_message(
            session,
            user=user,
            room_id=data.room_id,
            content=data.content,
            reply_to_id=data.reply_to_id,
        )
    except RoomNotFoundError:
        return GatewayCommandResponse(
            frames=[
                error_payload(
                    request_id=command.request_id,
                    code="room_not_found",
                    message="Room not found.",
                )
            ]
        )
    except RoomMembershipRequiredError:
        return GatewayCommandResponse(
            frames=[
                error_payload(
                    request_id=command.request_id,
                    code="room_membership_required",
                    message="Join the room before sending messages.",
                )
            ]
        )
    except MessageNotFoundError:
        return GatewayCommandResponse(
            frames=[
                error_payload(
                    request_id=command.request_id,
                    code="reply_target_not_found",
                    message="Reply target message not found.",
                )
            ]
        )
    except ProtocolError as exc:
        return GatewayCommandResponse(
            frames=[error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)]
        )

    await publish_notifications(message_with_event.notifications, signal_bus=signal_bus)
    return GatewayCommandResponse(
        frames=[
            ack_payload(request_id=command.request_id, event_id=str(message_with_event.event.id)),
            event_to_realtime_payload(message_with_event.event),
        ]
    )


async def handle_gateway_presence_update(
    *,
    command,
    session: DbSessionDep,
    user: User,
    presence_store: PresenceStoreDep,
    signal_bus: RealtimeSignalBusDep,
):
    try:
        data = parse_command_data(
            command,
            PresenceUpdateData,
            code="invalid_presence",
            message="presence.update requires room_id and status.",
        )
        await ensure_room_member(session, user=user, room_id=data.room_id)
    except RoomNotFoundError:
        return GatewayCommandResponse(
            frames=[
                error_payload(
                    request_id=command.request_id,
                    code="room_not_found",
                    message="Room not found.",
                )
            ]
        )
    except RoomMembershipRequiredError:
        return GatewayCommandResponse(
            frames=[
                error_payload(
                    request_id=command.request_id,
                    code="room_membership_required",
                    message="Join the room before updating presence.",
                )
            ]
        )
    except ProtocolError as exc:
        return GatewayCommandResponse(
            frames=[error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)]
        )

    await presence_store.mark_status(room_id=data.room_id, user_id=user.id, status=data.status)
    payload = presence_payload(room_id=str(data.room_id), user_id=str(user.id), status=data.status)
    await manager.broadcast_room(data.room_id, payload)
    await signal_bus.publish_room(room_id=data.room_id, payload=payload)
    return GatewayCommandResponse(frames=[ack_payload(request_id=command.request_id), payload])


async def handle_gateway_typing_update(
    *,
    command,
    session: DbSessionDep,
    user: User,
    typing_store: TypingStoreDep,
    signal_bus: RealtimeSignalBusDep,
):
    try:
        data = parse_command_data(
            command,
            TypingUpdateData,
            code="invalid_typing",
            message="typing.update requires room_id and status.",
        )
        await ensure_room_member(session, user=user, room_id=data.room_id)
    except RoomNotFoundError:
        return GatewayCommandResponse(
            frames=[
                error_payload(
                    request_id=command.request_id,
                    code="room_not_found",
                    message="Room not found.",
                )
            ]
        )
    except RoomMembershipRequiredError:
        return GatewayCommandResponse(
            frames=[
                error_payload(
                    request_id=command.request_id,
                    code="room_membership_required",
                    message="Join the room before updating typing state.",
                )
            ]
        )
    except ProtocolError as exc:
        return GatewayCommandResponse(
            frames=[error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)]
        )

    if data.status == "started":
        await typing_store.mark_started(room_id=data.room_id, user_id=user.id)
    else:
        await typing_store.mark_stopped(room_id=data.room_id, user_id=user.id)

    payload = typing_payload(room_id=str(data.room_id), user_id=str(user.id), status=data.status)
    await manager.broadcast_room(data.room_id, payload)
    await signal_bus.publish_room(room_id=data.room_id, payload=payload)
    return GatewayCommandResponse(frames=[ack_payload(request_id=command.request_id), payload])


async def authenticate_gateway_access_token(
    *,
    access_token: str,
    session: DbSessionDep,
    settings: Settings,
):
    try:
        claims = decode_token_claims(
            access_token,
            expected_type=TokenType.ACCESS,
            settings=settings,
        )
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
        ) from exc

    user = await get_user_by_id(session, claims.subject)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
        )
    return user, claims


def verify_gateway_token(*, gateway_token: str | None, settings: Settings) -> None:
    expected_token = settings.gateway_internal_token
    if expected_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway internal authentication is not configured.",
        )
    if gateway_token is None or not secrets.compare_digest(gateway_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid gateway credentials.",
        )
