from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbSessionDep
from app.schemas.read_state import RoomReadStateResponse, RoomReadStateUpdateRequest
from app.services.message import RoomMembershipRequiredError
from app.services.read_state import (
    ReadStateAheadOfRoomError,
    list_room_read_states,
    update_room_read_state,
)
from app.services.workspace import RoomNotFoundError

router = APIRouter(prefix="/rooms/{room_id}", tags=["read-states"])


@router.put("/read-state", response_model=RoomReadStateResponse)
async def update_room_read_state_endpoint(
    room_id: UUID,
    payload: RoomReadStateUpdateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> RoomReadStateResponse:
    try:
        read_state_with_event = await update_room_read_state(
            session,
            user=current_user,
            room_id=room_id,
            last_read_event_seq=payload.last_read_event_seq,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found."
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before updating read state.",
        ) from exc
    except ReadStateAheadOfRoomError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Read state cannot point beyond the latest room event.",
        ) from exc

    return RoomReadStateResponse.model_validate(read_state_with_event.read_state)


@router.get("/read-states", response_model=list[RoomReadStateResponse])
async def list_room_read_states_endpoint(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[RoomReadStateResponse]:
    try:
        read_states = await list_room_read_states(session, user=current_user, room_id=room_id)
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found."
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before reading read states.",
        ) from exc

    return [RoomReadStateResponse.model_validate(read_state) for read_state in read_states]
