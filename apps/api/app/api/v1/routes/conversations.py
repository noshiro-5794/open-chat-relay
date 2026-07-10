from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbSessionDep
from app.api.v1.routes.rooms import room_response
from app.schemas.conversation import (
    ConversationListResponse,
    DirectConversationRequest,
    GroupConversationCreateRequest,
)
from app.schemas.workspace import RoomResponse
from app.services.conversation import (
    create_group_conversation,
    list_conversations,
    selected_conversation_id,
    start_global_direct_conversation,
)
from app.services.workspace import SelfConversationError, SlugAlreadyExistsError, UserNotFoundError

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations_endpoint(
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> ConversationListResponse:
    conversations = await list_conversations(session, user=current_user)
    return ConversationListResponse(
        conversations=[room_response(conversation) for conversation in conversations],
        selected_conversation_id=selected_conversation_id(conversations),
    )


@router.post("/direct", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def start_direct_conversation_endpoint(
    payload: DirectConversationRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> RoomResponse:
    try:
        room = await start_global_direct_conversation(
            session,
            actor=current_user,
            target_email=payload.email,
        )
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


@router.post("/groups", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_group_conversation_endpoint(
    payload: GroupConversationCreateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> RoomResponse:
    try:
        room = await create_group_conversation(
            session,
            actor=current_user,
            name=payload.name,
            member_emails=payload.member_emails,
        )
    except SlugAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversation name is already in use.",
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        ) from exc
    except SelfConversationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already in this conversation.",
        ) from exc
    return room_response(room)
