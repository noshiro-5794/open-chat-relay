from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbSessionDep, PresenceStoreDep
from app.schemas.presence import PresenceUserResponse, RoomPresenceResponse
from app.services.message import RoomMembershipRequiredError, ensure_room_member
from app.services.workspace import RoomNotFoundError

router = APIRouter(prefix="/rooms/{room_id}/presence", tags=["presence"])


@router.get("", response_model=RoomPresenceResponse)
async def room_presence(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    presence_store: PresenceStoreDep,
) -> RoomPresenceResponse:
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
            detail="Join the room before reading presence.",
        ) from exc

    online_members = await presence_store.list_room(room_id=room_id)
    return RoomPresenceResponse(
        room_id=room_id,
        users=[
            PresenceUserResponse(user_id=member.user_id, status=member.status)
            for member in online_members
        ],
    )
