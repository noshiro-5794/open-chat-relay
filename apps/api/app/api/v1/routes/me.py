from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbSessionDep
from app.schemas.auth import UserResponse, UserUpdateRequest

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUserDep) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_me(
    payload: UserUpdateRequest,
    session: DbSessionDep,
    current_user: CurrentUserDep,
) -> UserResponse:
    current_user.display_name = payload.display_name.strip()
    await session.commit()
    await session.refresh(current_user)
    return UserResponse.model_validate(current_user)
