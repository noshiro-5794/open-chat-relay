from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUserDep, DbSessionDep
from app.schemas.reaction import ReactionCreateRequest, ReactionResponse
from app.services.message import MessageNotFoundError, RoomMembershipRequiredError
from app.services.reaction import (
    ReactionAlreadyExistsError,
    ReactionNotFoundError,
    add_reaction,
    remove_reaction,
)
from app.services.workspace import RoomNotFoundError

router = APIRouter(prefix="/rooms/{room_id}/messages/{message_id}/reactions", tags=["reactions"])

EmojiQuery = Annotated[str, Query(min_length=1, max_length=64)]


@router.post("", response_model=ReactionResponse, status_code=status.HTTP_201_CREATED)
async def add_reaction_endpoint(
    room_id: UUID,
    message_id: UUID,
    payload: ReactionCreateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> ReactionResponse:
    try:
        reaction_with_event = await add_reaction(
            session,
            user=current_user,
            room_id=room_id,
            message_id=message_id,
            emoji=payload.emoji,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before reacting to messages.",
        ) from exc
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found.",
        ) from exc
    except ReactionAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reaction already exists.",
        ) from exc

    return ReactionResponse.model_validate(reaction_with_event.reaction)


@router.delete("", response_model=ReactionResponse)
async def remove_reaction_endpoint(
    room_id: UUID,
    message_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
    emoji: EmojiQuery,
) -> ReactionResponse:
    try:
        reaction_with_event = await remove_reaction(
            session,
            user=current_user,
            room_id=room_id,
            message_id=message_id,
            emoji=emoji,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Join the room before removing reactions.",
        ) from exc
    except (MessageNotFoundError, ReactionNotFoundError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reaction not found.",
        ) from exc

    return ReactionResponse.model_validate(reaction_with_event.reaction)
