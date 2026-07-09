import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings, validate_startup_settings
from app.core.logging import configure_logging
from app.core.rate_limit import create_rate_limiter
from app.realtime.presence_store import create_presence_store
from app.realtime.redis_bus import redis_realtime_fanout_loop
from app.realtime.signal_bus import create_realtime_signal_bus
from app.realtime.typing_store import create_typing_store


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    validate_startup_settings(settings)
    docs_enabled = settings.effective_docs_enabled()
    rate_limiter = create_rate_limiter(settings)
    presence_store = create_presence_store(settings)
    typing_store = create_typing_store(settings)
    signal_bus = create_realtime_signal_bus(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings)
        app.state.settings = settings
        app.state.presence_store = presence_store
        app.state.typing_store = typing_store
        app.state.realtime_signal_bus = signal_bus
        fanout_task: asyncio.Task[None] | None = None
        if settings.effective_realtime_redis_fanout_enabled():
            fanout_task = asyncio.create_task(redis_realtime_fanout_loop(settings))
        try:
            yield
        finally:
            if fanout_task is not None:
                fanout_task.cancel()
                with suppress(asyncio.CancelledError):
                    await fanout_task
            await rate_limiter.close()
            await presence_store.close()
            await typing_store.close()
            await signal_bus.close()

    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        debug=settings.debug,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url=f"{settings.api_v1_prefix}/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.presence_store = presence_store
    app.state.typing_store = typing_store
    app.state.realtime_signal_bus = signal_bus

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def reject_large_requests(request: Request, call_next):
        content_length = request.headers.get("content-length")
        try:
            request_body_bytes = int(content_length) if content_length is not None else 0
        except ValueError:
            request_body_bytes = 0
        if request_body_bytes > settings.max_request_body_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                content={
                    "detail": "Request body is too large.",
                    "max_request_body_bytes": settings.max_request_body_bytes,
                },
            )
        return await call_next(request)

    @app.middleware("http")
    async def rate_limit_requests(request: Request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)

        decision = await rate_limiter.check(request)
        if not decision.allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "detail": "Rate limit exceeded.",
                    "category": decision.category,
                    "limit": decision.limit,
                    "retry_after_seconds": decision.retry_after_seconds,
                },
                headers={
                    "Retry-After": str(decision.retry_after_seconds),
                    "X-RateLimit-Limit": str(decision.limit),
                    "X-RateLimit-Remaining": str(decision.remaining),
                    "X-RateLimit-Category": decision.category,
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        response.headers["X-RateLimit-Category"] = decision.category
        return response

    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
