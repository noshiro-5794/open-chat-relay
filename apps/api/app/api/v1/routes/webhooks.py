from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.deps import DbSessionDep, RealtimeSignalBusDep
from app.api.v1.routes.messages import message_response
from app.models import Bot
from app.realtime.notifications import publish_notifications
from app.schemas.message import MessageResponse
from app.schemas.webhook import IncomingWebhookMessageRequest
from app.services.app import authenticate_incoming_webhook
from app.services.message import create_bot_message
from app.services.workspace import RoomNotFoundError

router = APIRouter(prefix="/webhooks/incoming", tags=["webhooks"])

webhook_secret_scheme = HTTPBearer(auto_error=False)
WebhookSecretDep = Annotated[HTTPAuthorizationCredentials | None, Depends(webhook_secret_scheme)]


@router.post(
    "/{webhook_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def deliver_incoming_webhook_endpoint(
    webhook_id: UUID,
    payload: IncomingWebhookMessageRequest,
    session: DbSessionDep,
    credentials: WebhookSecretDep,
    signal_bus: RealtimeSignalBusDep,
) -> MessageResponse:
    if credentials is None:
        raise_invalid_webhook_secret()

    webhook = await authenticate_incoming_webhook(
        session,
        webhook_id=webhook_id,
        secret=credentials.credentials,
    )
    if webhook is None:
        raise_invalid_webhook_secret()

    bot = await session.get(Bot, webhook.bot_id)
    if bot is None:
        raise_invalid_webhook_secret()

    try:
        message_with_event = await create_bot_message(
            session,
            bot=bot,
            room_id=webhook.room_id,
            content=payload.content,
            metadata=webhook_metadata(webhook_id=webhook_id, payload=payload),
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Incoming webhook target room is no longer available.",
        ) from exc

    await publish_notifications(message_with_event.notifications, signal_bus=signal_bus)
    return message_response(message_with_event.message, attachments=message_with_event.attachments)


def webhook_metadata(*, webhook_id: UUID, payload: IncomingWebhookMessageRequest) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "webhook_id": str(webhook_id),
        "kind": "incoming_webhook",
    }
    if payload.external_id is not None:
        metadata["external_id"] = payload.external_id
    if payload.source is not None:
        metadata["source"] = payload.source
    if payload.metadata:
        metadata["payload"] = payload.metadata
    return metadata


def raise_invalid_webhook_secret() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing webhook secret.",
        headers={"WWW-Authenticate": "Bearer"},
    )
