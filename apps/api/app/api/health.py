import redis.asyncio as redis
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DbSessionDep, SettingsDep
from app.schemas.health import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.project_name,
        version=settings.version,
        environment=settings.environment,
    )


@router.get("/ready", response_model=HealthResponse)
async def ready(
    settings: SettingsDep,
    session: DbSessionDep,
    response: Response,
) -> HealthResponse:
    checks: dict[str, str] = {}

    try:
        await session.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    if settings.environment == "test":
        checks["redis"] = "skipped"
    else:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        try:
            await redis_client.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "unavailable"
        finally:
            await redis_client.aclose()

    is_ready = all(value in {"ok", "skipped"} for value in checks.values())
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ready" if is_ready else "not_ready",
        service=settings.project_name,
        version=settings.version,
        environment=settings.environment,
        checks=checks,
    )
