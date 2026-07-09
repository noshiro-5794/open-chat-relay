from typing import Annotated

from fastapi import APIRouter, Depends, Query, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from app.api.deps import PresenceStoreDep, RealtimeSignalBusDep, SettingsDep, TypingStoreDep
from app.core.config import Settings
from app.core.security import TokenType, TokenValidationError, decode_token
from app.db.session import get_db_session
from app.models import User
from app.realtime.manager import manager
from app.realtime.notifications import publish_notifications
from app.realtime.presence_store import PresenceStore
from app.realtime.protocol import (
    COMMAND_MESSAGE_SEND,
    COMMAND_PRESENCE_UPDATE,
    COMMAND_ROOM_SUBSCRIBE,
    COMMAND_ROOM_UNSUBSCRIBE,
    COMMAND_TYPING_UPDATE,
    InboundCommand,
    MessageSendData,
    PresenceUpdateData,
    ProtocolError,
    RoomCommandData,
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
from app.realtime.signal_bus import RealtimeSignalBus
from app.realtime.typing_store import TypingStore
from app.services.auth import get_user_by_id
from app.services.message import (
    MessageNotFoundError,
    RoomMembershipRequiredError,
    create_message,
    ensure_room_member,
    list_room_events,
)
from app.services.workspace import RoomNotFoundError

router = APIRouter(tags=["realtime"])

TokenQuery = Annotated[str | None, Query()]
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    session: SessionDep,
    settings: SettingsDep,
    presence_store: PresenceStoreDep,
    typing_store: TypingStoreDep,
    signal_bus: RealtimeSignalBusDep,
    token: TokenQuery = None,
) -> None:
    user = await authenticate_websocket(token=token, session=session, settings=settings)
    if user is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    await manager.connect(websocket, user.id)

    try:
        while True:
            command = await websocket.receive_json()
            await handle_command(
                websocket=websocket,
                session=session,
                user=user,
                command=command,
                presence_store=presence_store,
                typing_store=typing_store,
                signal_bus=signal_bus,
            )
    except WebSocketDisconnect:
        offline = await manager.disconnect(websocket)
        for room_id, user_id in offline:
            await presence_store.mark_offline(room_id=room_id, user_id=user_id)
            await typing_store.mark_stopped(room_id=room_id, user_id=user_id)
            payload = presence_payload(room_id=str(room_id), user_id=str(user_id), status="offline")
            await manager.broadcast_room(
                room_id,
                payload,
            )
            await signal_bus.publish_room(room_id=room_id, payload=payload)


async def authenticate_websocket(
    *,
    token: str | None,
    session: AsyncSession,
    settings: Settings,
) -> User | None:
    if token is None:
        return None
    try:
        user_id = decode_token(token, expected_type=TokenType.ACCESS, settings=settings)
    except TokenValidationError:
        return None

    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        return None
    return user


async def handle_command(
    *,
    websocket: WebSocket,
    session: AsyncSession,
    user: User,
    command: object,
    presence_store: PresenceStore,
    typing_store: TypingStore,
    signal_bus: RealtimeSignalBus,
) -> None:
    try:
        parsed_command = parse_inbound_command(command)
    except ProtocolError as exc:
        await websocket.send_json(
            error_payload(
                request_id=exc.request_id,
                code=exc.code,
                message=exc.message,
            )
        )
        return

    if parsed_command.type == COMMAND_ROOM_SUBSCRIBE:
        await handle_subscribe(
            websocket=websocket,
            session=session,
            user=user,
            command=parsed_command,
            presence_store=presence_store,
            typing_store=typing_store,
            signal_bus=signal_bus,
        )
        return

    if parsed_command.type == COMMAND_ROOM_UNSUBSCRIBE:
        await handle_unsubscribe(
            websocket=websocket,
            command=parsed_command,
            presence_store=presence_store,
            typing_store=typing_store,
            signal_bus=signal_bus,
        )
        return

    if parsed_command.type == COMMAND_MESSAGE_SEND:
        await handle_message_send(
            websocket=websocket,
            session=session,
            user=user,
            command=parsed_command,
            signal_bus=signal_bus,
        )
        return

    if parsed_command.type == COMMAND_PRESENCE_UPDATE:
        await handle_presence_update(
            websocket=websocket,
            session=session,
            user=user,
            command=parsed_command,
            presence_store=presence_store,
            signal_bus=signal_bus,
        )
        return

    if parsed_command.type == COMMAND_TYPING_UPDATE:
        await handle_typing_update(
            websocket=websocket,
            session=session,
            user=user,
            command=parsed_command,
            typing_store=typing_store,
            signal_bus=signal_bus,
        )
        return

    await websocket.send_json(
        error_payload(
            request_id=parsed_command.request_id,
            code="unknown_command",
            message="Unknown realtime command.",
        )
    )


async def handle_subscribe(
    *,
    websocket: WebSocket,
    session: AsyncSession,
    user: User,
    command: InboundCommand,
    presence_store: PresenceStore,
    typing_store: TypingStore,
    signal_bus: RealtimeSignalBus,
) -> None:
    try:
        data = parse_command_data(
            command,
            RoomSubscribeData,
            code="invalid_room_id",
            message="Invalid room_id.",
        )
    except ProtocolError as exc:
        await websocket.send_json(
            error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)
        )
        return

    try:
        await ensure_room_member(session, user=user, room_id=data.room_id)
    except RoomNotFoundError:
        await websocket.send_json(
            error_payload(
                request_id=command.request_id,
                code="room_not_found",
                message="Room not found.",
            )
        )
        return
    except RoomMembershipRequiredError:
        await websocket.send_json(
            error_payload(
                request_id=command.request_id,
                code="room_membership_required",
                message="Join the room before subscribing.",
            )
        )
        return

    became_online = await manager.subscribe(websocket, data.room_id)
    if became_online:
        await presence_store.mark_online(room_id=data.room_id, user_id=user.id)
    await websocket.send_json(ack_payload(request_id=command.request_id))
    if data.last_event_seq is not None:
        missed_events = await list_room_events(
            session,
            user=user,
            room_id=data.room_id,
            after_seq=data.last_event_seq,
            limit=100,
        )
        for event in missed_events:
            await websocket.send_json(event_to_realtime_payload(event))

    if became_online:
        payload = presence_payload(room_id=str(data.room_id), user_id=str(user.id), status="online")
        await manager.broadcast_room(
            data.room_id,
            payload,
            exclude=websocket,
        )
        await signal_bus.publish_room(room_id=data.room_id, payload=payload)


async def handle_unsubscribe(
    *,
    websocket: WebSocket,
    command: InboundCommand,
    presence_store: PresenceStore,
    typing_store: TypingStore,
    signal_bus: RealtimeSignalBus,
) -> None:
    try:
        data = parse_command_data(
            command,
            RoomCommandData,
            code="invalid_room_id",
            message="Invalid room_id.",
        )
    except ProtocolError as exc:
        await websocket.send_json(
            error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)
        )
        return

    became_offline = await manager.unsubscribe(websocket, data.room_id)
    user_id = manager.connection_user_id(websocket)
    if became_offline:
        await presence_store.mark_offline(room_id=data.room_id, user_id=user_id)
        await typing_store.mark_stopped(room_id=data.room_id, user_id=user_id)
    await websocket.send_json(ack_payload(request_id=command.request_id))
    if became_offline:
        payload = presence_payload(
            room_id=str(data.room_id),
            user_id=str(user_id),
            status="offline",
        )
        await manager.broadcast_room(
            data.room_id,
            payload,
            exclude=websocket,
        )
        await signal_bus.publish_room(room_id=data.room_id, payload=payload)


async def handle_message_send(
    *,
    websocket: WebSocket,
    session: AsyncSession,
    user: User,
    command: InboundCommand,
    signal_bus: RealtimeSignalBus,
) -> None:
    try:
        data = parse_command_data(
            command,
            MessageSendData,
            code="invalid_message",
            message="message.send requires room_id and content.",
        )
    except ProtocolError as exc:
        await websocket.send_json(
            error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)
        )
        return

    try:
        message_with_event = await create_message(
            session,
            user=user,
            room_id=data.room_id,
            content=data.content,
            reply_to_id=data.reply_to_id,
        )
    except RoomNotFoundError:
        await websocket.send_json(
            error_payload(
                request_id=command.request_id,
                code="room_not_found",
                message="Room not found.",
            )
        )
        return
    except RoomMembershipRequiredError:
        await websocket.send_json(
            error_payload(
                request_id=command.request_id,
                code="room_membership_required",
                message="Join the room before sending messages.",
            )
        )
        return
    except MessageNotFoundError:
        await websocket.send_json(
            error_payload(
                request_id=command.request_id,
                code="reply_target_not_found",
                message="Reply target message not found.",
            )
        )
        return

    event_payload = event_to_realtime_payload(message_with_event.event)
    await websocket.send_json(
        ack_payload(request_id=command.request_id, event_id=str(message_with_event.event.id))
    )
    await publish_notifications(message_with_event.notifications, signal_bus=signal_bus)
    await manager.broadcast_room(data.room_id, event_payload)


async def handle_presence_update(
    *,
    websocket: WebSocket,
    session: AsyncSession,
    user: User,
    command: InboundCommand,
    presence_store: PresenceStore,
    signal_bus: RealtimeSignalBus,
) -> None:
    try:
        data = parse_command_data(
            command,
            PresenceUpdateData,
            code="invalid_presence",
            message="presence.update requires room_id and status.",
        )
    except ProtocolError as exc:
        await websocket.send_json(
            error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)
        )
        return

    try:
        await ensure_room_member(session, user=user, room_id=data.room_id)
    except RoomNotFoundError:
        await websocket.send_json(
            error_payload(
                request_id=command.request_id,
                code="room_not_found",
                message="Room not found.",
            )
        )
        return
    except RoomMembershipRequiredError:
        await websocket.send_json(
            error_payload(
                request_id=command.request_id,
                code="room_membership_required",
                message="Join the room before updating presence.",
            )
        )
        return

    await presence_store.mark_status(room_id=data.room_id, user_id=user.id, status=data.status)
    await websocket.send_json(ack_payload(request_id=command.request_id))
    payload = presence_payload(room_id=str(data.room_id), user_id=str(user.id), status=data.status)
    await manager.broadcast_room(
        data.room_id,
        payload,
        exclude=websocket,
    )
    await signal_bus.publish_room(room_id=data.room_id, payload=payload)


async def handle_typing_update(
    *,
    websocket: WebSocket,
    session: AsyncSession,
    user: User,
    command: InboundCommand,
    typing_store: TypingStore,
    signal_bus: RealtimeSignalBus,
) -> None:
    try:
        data = parse_command_data(
            command,
            TypingUpdateData,
            code="invalid_typing",
            message="typing.update requires room_id and status.",
        )
    except ProtocolError as exc:
        await websocket.send_json(
            error_payload(request_id=exc.request_id, code=exc.code, message=exc.message)
        )
        return

    try:
        await ensure_room_member(session, user=user, room_id=data.room_id)
    except RoomNotFoundError:
        await websocket.send_json(
            error_payload(
                request_id=command.request_id,
                code="room_not_found",
                message="Room not found.",
            )
        )
        return
    except RoomMembershipRequiredError:
        await websocket.send_json(
            error_payload(
                request_id=command.request_id,
                code="room_membership_required",
                message="Join the room before updating typing state.",
            )
        )
        return

    if data.status == "started":
        await typing_store.mark_started(room_id=data.room_id, user_id=user.id)
    else:
        await typing_store.mark_stopped(room_id=data.room_id, user_id=user.id)

    await websocket.send_json(ack_payload(request_id=command.request_id))
    payload = typing_payload(room_id=str(data.room_id), user_id=str(user.id), status=data.status)
    await manager.broadcast_room(
        data.room_id,
        payload,
        exclude=websocket,
    )
    await signal_bus.publish_room(room_id=data.room_id, payload=payload)
