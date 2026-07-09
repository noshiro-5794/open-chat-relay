from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import DbSessionDep, RealtimeSignalBusDep
from app.api.v1.routes.messages import message_response
from app.realtime.notifications import publish_notifications
from app.schemas.message import MessageCreateRequest, MessageResponse
from app.services.app import BotNotFoundError, authenticate_api_key, get_bot_for_app
from app.services.message import (
    AttachmentNotFoundError,
    MessageNotFoundError,
    create_bot_message,
)
from app.services.workspace import RoomNotFoundError

router = APIRouter(prefix="/app", tags=["app-api"])

api_key_scheme = HTTPBearer(auto_error=False)
ApiKeyBearerDep = Annotated[HTTPAuthorizationCredentials | None, Depends(api_key_scheme)]


@router.post(
    "/rooms/{room_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_app_message_endpoint(
    room_id: UUID,
    payload: MessageCreateRequest,
    session: DbSessionDep,
    credentials: ApiKeyBearerDep,
    signal_bus: RealtimeSignalBusDep,
) -> MessageResponse:
    if credentials is None:
        raise_invalid_api_key()

    api_key = await authenticate_api_key(session, secret=credentials.credentials)
    if api_key is None:
        raise_invalid_api_key()

    try:
        bot = await get_bot_for_app(session, app_id=api_key.app_id)
        if bot.workspace_id != api_key.workspace_id:
            raise BotNotFoundError
        message_with_event = await create_bot_message(
            session,
            bot=bot,
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
    except BotNotFoundError:
        raise_invalid_api_key()
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


def raise_invalid_api_key() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key.",
        headers={"WWW-Authenticate": "Bearer"},
    )
