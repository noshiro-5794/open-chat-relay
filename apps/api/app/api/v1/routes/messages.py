from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUserDep, DbSessionDep, RealtimeSignalBusDep
from app.models import Attachment, Event, Message
from app.realtime.notifications import publish_notifications
from app.schemas.attachment import AttachmentResponse
from app.schemas.message import (
    EventResponse,
    MessageCreateRequest,
    MessagePageResponse,
    MessageResponse,
    MessageUpdateRequest,
)
from app.services.message import (
    AttachmentNotFoundError,
    MessageNotFoundError,
    MessagePermissionDeniedError,
    RoomMembershipRequiredError,
    create_message,
    delete_message,
    list_attachments_for_messages,
    list_message_replies,
    list_messages,
    list_messages_page,
    list_room_events,
    search_messages,
    update_message,
)
from app.services.workspace import RoomNotFoundError

router = APIRouter(prefix="/rooms/{room_id}", tags=["messages"])

LimitQuery = Annotated[int, Query(ge=1, le=100)]
AfterSeqQuery = Annotated[int | None, Query(ge=0)]
SearchQuery = Annotated[str, Query(min_length=1, max_length=200)]
BeforeMessageQuery = Annotated[UUID | None, Query()]


@router.post("/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message_endpoint(
    room_id: UUID,
    payload: MessageCreateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    signal_bus: RealtimeSignalBusDep,
) -> MessageResponse:
    try:
        message_with_event = await create_message(
            session,
            user=current_user,
            room_id=room_id,
            content=payload.content,
            attachment_ids=payload.attachment_ids,
            reply_to_id=payload.reply_to_id,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before sending messages.",
        ) from exc
    except AttachmentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found.",
        ) from exc
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reply target message not found.",
        ) from exc

    await publish_notifications(message_with_event.notifications, signal_bus=signal_bus)
    return message_response(message_with_event.message, attachments=message_with_event.attachments)


@router.patch("/messages/{message_id}", response_model=MessageResponse)
async def update_message_endpoint(
    room_id: UUID,
    message_id: UUID,
    payload: MessageUpdateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> MessageResponse:
    try:
        message_with_event = await update_message(
            session,
            user=current_user,
            room_id=room_id,
            message_id=message_id,
            content=payload.content,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before updating messages.",
        ) from exc
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found.",
        ) from exc
    except MessagePermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the sender can update this message.",
        ) from exc

    return message_response(message_with_event.message, attachments=message_with_event.attachments)


@router.delete("/messages/{message_id}", response_model=MessageResponse)
async def delete_message_endpoint(
    room_id: UUID,
    message_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> MessageResponse:
    try:
        message_with_event = await delete_message(
            session,
            user=current_user,
            room_id=room_id,
            message_id=message_id,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before deleting messages.",
        ) from exc
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found.",
        ) from exc
    except MessagePermissionDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the sender can delete this message.",
        ) from exc

    return message_response(message_with_event.message, attachments=message_with_event.attachments)


@router.get("/messages", response_model=list[MessageResponse])
async def list_messages_endpoint(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    limit: LimitQuery = 50,
) -> list[MessageResponse]:
    try:
        messages = await list_messages(
            session,
            user=current_user,
            room_id=room_id,
            limit=limit,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before reading messages.",
        ) from exc

    attachments_by_message = await list_attachments_for_messages(
        session,
        message_ids=[message.id for message in messages],
    )
    return [
        message_response(message, attachments=attachments_by_message.get(message.id, []))
        for message in messages
    ]


@router.get("/messages/page", response_model=MessagePageResponse)
async def list_messages_page_endpoint(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    limit: LimitQuery = 50,
    before_message_id: BeforeMessageQuery = None,
) -> MessagePageResponse:
    try:
        page = await list_messages_page(
            session,
            user=current_user,
            room_id=room_id,
            limit=limit,
            before_message_id=before_message_id,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before reading messages.",
        ) from exc
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message cursor not found.",
        ) from exc

    attachments_by_message = await list_attachments_for_messages(
        session,
        message_ids=[message.id for message in page.messages],
    )
    return MessagePageResponse(
        items=[
            message_response(message, attachments=attachments_by_message.get(message.id, []))
            for message in page.messages
        ],
        next_before_message_id=page.next_before_message_id,
        has_more=page.has_more,
    )


@router.get("/messages/search", response_model=list[MessageResponse])
async def search_messages_endpoint(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    q: SearchQuery,
    limit: LimitQuery = 50,
) -> list[MessageResponse]:
    try:
        messages = await search_messages(
            session,
            user=current_user,
            room_id=room_id,
            query=q,
            limit=limit,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before searching messages.",
        ) from exc

    attachments_by_message = await list_attachments_for_messages(
        session,
        message_ids=[message.id for message in messages],
    )
    return [
        message_response(message, attachments=attachments_by_message.get(message.id, []))
        for message in messages
    ]


@router.get("/messages/{message_id}/replies", response_model=list[MessageResponse])
async def list_message_replies_endpoint(
    room_id: UUID,
    message_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    limit: LimitQuery = 100,
) -> list[MessageResponse]:
    try:
        messages = await list_message_replies(
            session,
            user=current_user,
            room_id=room_id,
            message_id=message_id,
            limit=limit,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before reading replies.",
        ) from exc
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found.",
        ) from exc

    attachments_by_message = await list_attachments_for_messages(
        session,
        message_ids=[message.id for message in messages],
    )
    return [
        message_response(message, attachments=attachments_by_message.get(message.id, []))
        for message in messages
    ]


@router.get("/events", response_model=list[EventResponse])
async def list_room_events_endpoint(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    after_seq: AfterSeqQuery = None,
    limit: LimitQuery = 100,
) -> list[EventResponse]:
    try:
        events = await list_room_events(
            session,
            user=current_user,
            room_id=room_id,
            after_seq=after_seq,
            limit=limit,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before reading events.",
        ) from exc

    return [event_response(event) for event in events]


def message_response(
    message: Message,
    *,
    attachments: list[Attachment] | None = None,
) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        workspace_id=message.workspace_id,
        room_id=message.room_id,
        sender_type=message.sender_type,
        sender_id=message.sender_id,
        sender_bot_id=message.sender_bot_id,
        message_type=message.message_type,
        content=message.content,
        reply_to_id=message.reply_to_id,
        created_at=message.created_at,
        updated_at=message.updated_at,
        deleted_at=message.deleted_at,
        attachments=[
            AttachmentResponse.model_validate(attachment)
            for attachment in (attachments if attachments is not None else [])
        ],
    )


def event_response(event: Event) -> EventResponse:
    return EventResponse(
        id=event.id,
        type=event.event_type,
        workspace_id=event.workspace_id,
        room_id=event.room_id,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        actor_bot_id=event.actor_bot_id,
        room_event_seq=event.room_event_seq,
        workspace_event_seq=event.workspace_event_seq,
        lane=event.lane,
        reliability=event.reliability,
        ordering=event.ordering,
        priority=event.priority,
        ttl_ms=event.ttl_ms,
        created_at=event.created_at,
        data=event.payload,
    )
