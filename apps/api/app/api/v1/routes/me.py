from fastapi import APIRouter

from app.api.deps import CurrentUserDep
from app.schemas.auth import UserResponse

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUserDep) -> UserResponse:
    return UserResponse.model_validate(current_user)
