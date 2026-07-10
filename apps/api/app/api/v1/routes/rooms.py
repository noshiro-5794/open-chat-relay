from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbSessionDep
from app.schemas.workspace import (
    DirectConversationCreateRequest,
    MembershipStatusResponse,
    RoomCreateRequest,
    RoomMemberAddRequest,
    RoomMemberInviteRequest,
    RoomMemberResponse,
    RoomMemberUpdateRequest,
    RoomResponse,
)
from app.services.workspace import (
    RoomLastOwnerError,
    RoomMemberNotFoundError,
    RoomMemberWithUser,
    RoomNotFoundError,
    RoomOwnerRequiredError,
    RoomWithRole,
    SelfConversationError,
    SlugAlreadyExistsError,
    UserNotFoundError,
    WorkspaceMembershipRequiredError,
    WorkspaceNotFoundError,
    add_room_member,
    create_room,
    get_room_for_user,
    invite_room_member_by_email,
    join_room,
    leave_room,
    list_room_members,
    list_rooms,
    remove_room_member,
    start_direct_conversation,
    update_room_member_role,
)

workspace_router = APIRouter(prefix="/workspaces/{workspace_id}/rooms", tags=["rooms"])
room_router = APIRouter(prefix="/rooms", tags=["rooms"])


@workspace_router.post("", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room_endpoint(
    workspace_id: UUID,
    payload: RoomCreateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> RoomResponse:
    try:
        room = await create_room(
            session,
            user=current_user,
            workspace_id=workspace_id,
            name=payload.name,
            slug=payload.slug,
            is_private=payload.is_private,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc
    except SlugAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room slug is already in use.",
        ) from exc

    return room_response(room)


@workspace_router.get("", response_model=list[RoomResponse])
async def list_rooms_endpoint(
    workspace_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[RoomResponse]:
    try:
        rooms = await list_rooms(session, user=current_user, workspace_id=workspace_id)
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc

    return [room_response(room) for room in rooms]


@workspace_router.post(
    "/direct",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_direct_conversation_endpoint(
    workspace_id: UUID,
    payload: DirectConversationCreateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> RoomResponse:
    try:
        room = await start_direct_conversation(
            session,
            actor=current_user,
            workspace_id=workspace_id,
            target_email=payload.email,
        )
    except WorkspaceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        ) from exc
    except SelfConversationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot start a direct conversation with yourself.",
        ) from exc

    return room_response(room)


@room_router.get("/{room_id}", response_model=RoomResponse)
async def get_room_endpoint(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> RoomResponse:
    try:
        room = await get_room_for_user(session, user=current_user, room_id=room_id)
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc

    return room_response(room)


@room_router.post("/{room_id}/join", response_model=MembershipStatusResponse)
async def join_room_endpoint(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> MembershipStatusResponse:
    try:
        room = await join_room(session, user=current_user, room_id=room_id)
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc

    return MembershipStatusResponse(status="joined", room=room_response(room))


@room_router.post("/{room_id}/leave", response_model=MembershipStatusResponse)
async def leave_room_endpoint(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> MembershipStatusResponse:
    try:
        room = await leave_room(session, user=current_user, room_id=room_id)
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found.",
        ) from exc
    except RoomLastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room must keep at least one owner.",
        ) from exc

    return MembershipStatusResponse(status="left", room=room_response(room))


@room_router.get("/{room_id}/members", response_model=list[RoomMemberResponse])
async def list_room_members_endpoint(
    room_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> list[RoomMemberResponse]:
    try:
        members = await list_room_members(session, user=current_user, room_id=room_id)
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found."
        ) from exc

    return [room_member_response(member) for member in members]


@room_router.post(
    "/{room_id}/members",
    response_model=RoomMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_room_member_endpoint(
    room_id: UUID,
    payload: RoomMemberAddRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> RoomMemberResponse:
    try:
        member = await add_room_member(
            session,
            actor=current_user,
            room_id=room_id,
            user_id=payload.user_id,
            role=payload.role,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found."
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        ) from exc
    except WorkspaceMembershipRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User must be a workspace member before joining a room.",
        ) from exc
    except RoomOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only room owners or workspace owners can manage room members.",
        ) from exc

    return room_member_response(member)


@room_router.post(
    "/{room_id}/invites",
    response_model=RoomMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def invite_room_member_endpoint(
    room_id: UUID,
    payload: RoomMemberInviteRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> RoomMemberResponse:
    try:
        member = await invite_room_member_by_email(
            session,
            actor=current_user,
            room_id=room_id,
            email=payload.email,
            role=payload.role,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found."
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
        ) from exc
    except SelfConversationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already in this conversation.",
        ) from exc
    except RoomOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only room owners or workspace owners can invite room members.",
        ) from exc

    return room_member_response(member)


@room_router.patch("/{room_id}/members/{user_id}", response_model=RoomMemberResponse)
async def update_room_member_endpoint(
    room_id: UUID,
    user_id: UUID,
    payload: RoomMemberUpdateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> RoomMemberResponse:
    try:
        member = await update_room_member_role(
            session,
            actor=current_user,
            room_id=room_id,
            user_id=user_id,
            role=payload.role,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found."
        ) from exc
    except RoomMemberNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room member not found.",
        ) from exc
    except RoomOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only room owners or workspace owners can manage room members.",
        ) from exc
    except RoomLastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room must keep at least one owner.",
        ) from exc

    return room_member_response(member)


@room_router.delete("/{room_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_room_member_endpoint(
    room_id: UUID,
    user_id: UUID,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> None:
    try:
        await remove_room_member(
            session,
            actor=current_user,
            room_id=room_id,
            user_id=user_id,
        )
    except RoomNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found."
        ) from exc
    except RoomMemberNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room member not found.",
        ) from exc
    except RoomOwnerRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only room owners or workspace owners can manage room members.",
        ) from exc
    except RoomLastOwnerError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Room must keep at least one owner.",
        ) from exc


def room_response(room: RoomWithRole) -> RoomResponse:
    return RoomResponse(
        id=room.room.id,
        workspace_id=room.room.workspace_id,
        name=room.room.name,
        slug=room.room.slug,
        is_private=room.room.is_private,
        role=room.role,
    )


def room_member_response(member: RoomMemberWithUser) -> RoomMemberResponse:
    return RoomMemberResponse(
        id=member.room_member.id,
        room_id=member.room_member.room_id,
        user_id=member.user.id,
        email=member.user.email,
        display_name=member.user.display_name,
        role=member.room_member.role,
    )
