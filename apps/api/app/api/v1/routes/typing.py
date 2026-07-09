from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbSessionDep, TypingStoreDep
from app.schemas.typing import RoomTypingResponse, TypingUserResponse
from app.services.message import RoomMembershipRequiredError, ensure_room_member
from app.services.workspace import RoomNotFoundError

router = APIRouter(prefix="/rooms/{room_id}/typing", tags=["typing"])


@router.get("", response_model=RoomTypingResponse)
async def room_typing(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    typing_store: TypingStoreDep,
) -> RoomTypingResponse:
    try:
        await ensure_room_member(session, user=current_user, room_id=room_id)
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before reading typing state.",
        ) from exc

    typing_members = await typing_store.list_room(room_id=room_id)
    return RoomTypingResponse(
        room_id=room_id,
        users=[
            TypingUserResponse(user_id=member.user_id, status="started")
            for member in typing_members
        ],
    )
