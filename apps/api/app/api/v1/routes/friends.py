from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbSessionDep
from app.schemas.friend import FriendAddRequest, FriendResponse
from app.services.friend import (
    FriendNotFoundError,
    FriendWithUser,
    SelfFriendError,
    UserNotFoundError,
    add_friend_by_email,
    list_friends,
    remove_friend,
)

router = APIRouter(prefix="/friends", tags=["friends"])


@router.get("", response_model=list[FriendResponse])
async def list_friends_endpoint(
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[FriendResponse]:
    friends = await list_friends(session, user=current_user)
    return [friend_response(friend) for friend in friends]


@router.post("", response_model=FriendResponse, status_code=status.HTTP_201_CREATED)
async def add_friend_endpoint(
    payload: FriendAddRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> FriendResponse:
    try:
        friend = await add_friend_by_email(session, user=current_user, email=payload.email)
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        ) from exc
    except SelfFriendError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot add yourself as a friend.",
        ) from exc
    return friend_response(friend)


@router.delete("/{friend_user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_friend_endpoint(
    friend_user_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> None:
    try:
        await remove_friend(session, user=current_user, friend_user_id=friend_user_id)
    except FriendNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Friend not found.",
        ) from exc


def friend_response(friend: FriendWithUser) -> FriendResponse:
    return FriendResponse(
        id=friend.contact.id,
        user_id=friend.user.id,
        email=friend.user.email,
        display_name=friend.user.display_name,
        created_at=friend.contact.created_at,
    )
