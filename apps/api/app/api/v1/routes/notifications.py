from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUserDep, DbSessionDep
from app.schemas.notification import NotificationResponse, UnreadNotificationCountResponse
from app.services.notification import (
    NotificationNotFoundError,
    list_user_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    unread_notification_count,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])

LimitQuery = Annotated[int, Query(ge=1, le=100)]


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    current_user: CurrentUserDep,
    session: DbSessionDep,
    limit: LimitQuery = 50,
    unread_only: bool = False,
) -> list[NotificationResponse]:
    notifications = await list_user_notifications(
        session,
        user_id=current_user.id,
        limit=limit,
        unread_only=unread_only,
    )
    return [NotificationResponse.model_validate(notification) for notification in notifications]


@router.get("/unread-count", response_model=UnreadNotificationCountResponse)
async def get_unread_notification_count(
    current_user: CurrentUserDep,
    session: DbSessionDep,
) -> UnreadNotificationCountResponse:
    count = await unread_notification_count(session, user_id=current_user.id)
    return UnreadNotificationCountResponse(unread_count=count)


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_read(
    notification_id: UUID,
    current_user: CurrentUserDep,
    session: DbSessionDep,
) -> NotificationResponse:
    try:
        notification = await mark_notification_read(
            session,
            user_id=current_user.id,
            notification_id=notification_id,
        )
    except NotificationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found.",
        ) from exc
    return NotificationResponse.model_validate(notification)


@router.post("/read-all")
async def mark_all_read(
    current_user: CurrentUserDep,
    session: DbSessionDep,
) -> dict[str, int]:
    updated = await mark_all_notifications_read(session, user_id=current_user.id)
    return {"updated": updated}
