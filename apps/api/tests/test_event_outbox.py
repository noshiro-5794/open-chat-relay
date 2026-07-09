from collections.abc import AsyncIterator

import pytest_asyncio
from app.db.base import Base
from app.models import EventOutbox, User
from app.services.message import create_message
from app.services.outbox import publish_pending_outbox_batch
from app.services.workspace import create_room, create_workspace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class FakePublisher:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> None:
        self.messages.append((channel, message))


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_durable_message_event_is_enqueued_to_outbox(session: AsyncSession) -> None:
    user = User(
        email="outbox@example.com",
        display_name="Outbox",
        password_hash="not-used-in-this-test",  # noqa: S106
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    workspace = await create_workspace(session, user=user, name="Outbox Team", slug=None)
    room = await create_room(
        session,
        user=user,
        workspace_id=workspace.workspace.id,
        name="General",
        slug=None,
        is_private=False,
    )
    message_with_event = await create_message(
        session,
        user=user,
        room_id=room.room.id,
        content="hello outbox",
    )

    result = await session.execute(
        select(EventOutbox).where(EventOutbox.event_id == message_with_event.event.id)
    )
    outbox = result.scalar_one()

    assert outbox.status == "pending"
    assert outbox.workspace_id == message_with_event.event.workspace_id
    assert outbox.room_id == message_with_event.event.room_id
    assert outbox.payload["type"] == "message.created"
    assert outbox.payload["data"]["content"] == "hello outbox"


async def test_pending_outbox_batch_is_published(session: AsyncSession) -> None:
    user = User(
        email="publisher@example.com",
        display_name="Publisher",
        password_hash="not-used-in-this-test",  # noqa: S106
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    workspace = await create_workspace(session, user=user, name="Publisher Team", slug=None)
    room = await create_room(
        session,
        user=user,
        workspace_id=workspace.workspace.id,
        name="General",
        slug=None,
        is_private=False,
    )
    await create_message(
        session,
        user=user,
        room_id=room.room.id,
        content="publish me",
    )

    publisher = FakePublisher()
    result = await publish_pending_outbox_batch(
        session,
        publisher=publisher,
        channel_prefix="test",
        limit=10,
        max_attempts=3,
    )
    outbox = (await session.execute(select(EventOutbox))).scalar_one()

    assert result.published == 1
    assert result.failed == 0
    assert outbox.status == "published"
    assert publisher.messages[0][0] == f"test:rooms:{room.room.id}:events"
    assert "message.created" in publisher.messages[0][1]
