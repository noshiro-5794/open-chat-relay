import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from app.api.deps import get_db_session
from app.core.config import Settings
from app.db.base import Base
from app.main import create_app
from app.models import (
    ApiKey,
    App,
    Attachment,
    AuditLog,
    AuthSession,
    Bot,
    Event,
    EventOutbox,
    IncomingWebhook,
    Membership,
    Message,
    MessageReaction,
    Notification,
    Room,
    RoomMember,
    RoomReadState,
    SystemAuditLog,
    User,
    UserContact,
    Workspace,
)
from app.realtime.manager import manager
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

_models = (
    ApiKey,
    App,
    Attachment,
    AuthSession,
    AuditLog,
    Bot,
    Event,
    EventOutbox,
    IncomingWebhook,
    Membership,
    Message,
    MessageReaction,
    Notification,
    Room,
    RoomMember,
    RoomReadState,
    SystemAuditLog,
    User,
    UserContact,
    Workspace,
)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    manager.reset()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            gateway_internal_token="test-gateway-token",  # noqa: S106
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url="redis://localhost:6379/15",
        )
    )
    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    await engine.dispose()
    manager.reset()


@pytest.fixture
def sync_client() -> Iterator[TestClient]:
    manager.reset()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def setup_database() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(setup_database())

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app = create_app(
        Settings(
            environment="test",
            jwt_secret_key="test-secret-at-least-32-bytes-long",  # noqa: S106
            gateway_internal_token="test-gateway-token",  # noqa: S106
            database_url="sqlite+aiosqlite:///:memory:",
            redis_url="redis://localhost:6379/15",
        )
    )
    app.dependency_overrides[get_db_session] = override_get_db_session

    with TestClient(app) as test_client:
        yield test_client

    asyncio.run(engine.dispose())
    manager.reset()
