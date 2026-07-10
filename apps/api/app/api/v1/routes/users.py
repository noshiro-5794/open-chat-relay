from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import Select, or_, select

from app.api.deps import CurrentUserDep, DbSessionDep
from app.models import User
from app.schemas.auth import UserResponse

router = APIRouter(prefix="/users", tags=["users"])

LimitQuery = Annotated[int, Query(ge=1, le=100)]  # noqa: UP040
SearchQuery = Annotated[str | None, Query(min_length=1, max_length=120)]  # noqa: UP040


@router.get("", response_model=list[UserResponse])
async def list_users(
    session: DbSessionDep,
    _current_user: CurrentUserDep,
    q: SearchQuery = None,
    limit: LimitQuery = 50,
) -> list[UserResponse]:
    statement: Select[tuple[User]] = select(User).where(User.is_active.is_(True))
    if q is not None:
        query = f"%{q.strip().lower()}%"
        statement = statement.where(
            or_(
                User.email.ilike(query),
                User.display_name.ilike(query),
            )
        )
    statement = statement.order_by(User.display_name, User.email).limit(limit)
    result = await session.execute(statement)
    return [UserResponse.model_validate(user) for user in result.scalars().all()]
