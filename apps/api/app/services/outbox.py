import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, EventOutbox, EventOutboxStatus
from app.realtime.serializers import event_to_realtime_payload


class OutboxPublisher(Protocol):
    async def publish(self, channel: str, message: str) -> None: ...


@dataclass(frozen=True)
class OutboxPublishResult:
    published: int
    failed: int


async def enqueue_event_outbox(session: AsyncSession, *, event: Event) -> EventOutbox:
    outbox = EventOutbox(
        event_id=event.id,
        workspace_id=event.workspace_id,
        room_id=event.room_id,
        status=EventOutboxStatus.PENDING.value,
        attempts=0,
        payload=event_to_realtime_payload(event),
    )
    session.add(outbox)
    return outbox


async def publish_pending_outbox_batch(
    session: AsyncSession,
    *,
    publisher: OutboxPublisher,
    channel_prefix: str,
    limit: int,
    max_attempts: int,
) -> OutboxPublishResult:
    outbox_rows = await list_pending_outbox(session, limit=limit)
    published = 0
    failed = 0

    for outbox in outbox_rows:
        outbox.attempts += 1
        try:
            await publisher.publish(
                outbox_channel(outbox, channel_prefix=channel_prefix),
                json.dumps(outbox.payload, separators=(",", ":"), default=str),
            )
        except Exception as exc:
            outbox.last_error = str(exc)[:1000]
            if outbox.attempts >= max_attempts:
                outbox.status = EventOutboxStatus.FAILED.value
                failed += 1
            continue

        outbox.status = EventOutboxStatus.PUBLISHED.value
        outbox.last_error = None
        published += 1

    await session.commit()
    return OutboxPublishResult(published=published, failed=failed)


async def list_pending_outbox(session: AsyncSession, *, limit: int) -> list[EventOutbox]:
    now = datetime.now(UTC)
    statement: Select[tuple[EventOutbox]] = (
        select(EventOutbox)
        .where(
            EventOutbox.status == EventOutboxStatus.PENDING.value,
            (EventOutbox.next_attempt_at.is_(None)) | (EventOutbox.next_attempt_at <= now),
        )
        .order_by(EventOutbox.created_at)
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


def outbox_channel(outbox: EventOutbox, *, channel_prefix: str) -> str:
    if outbox.room_id is not None:
        return f"{channel_prefix}:rooms:{outbox.room_id}:events"
    return f"{channel_prefix}:workspaces:{outbox.workspace_id}:events"
