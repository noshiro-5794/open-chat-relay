from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class Event(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("room_id", "room_event_seq", name="uq_events_room_id_room_event_seq"),
        UniqueConstraint(
            "workspace_id",
            "workspace_event_seq",
            name="uq_events_workspace_id_workspace_event_seq",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    room_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    actor_type: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    actor_bot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bots.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    room_event_seq: Mapped[int | None] = mapped_column(nullable=True)
    workspace_event_seq: Mapped[int] = mapped_column(nullable=False)
    lane: Mapped[str] = mapped_column(String(32), nullable=False)
    reliability: Mapped[str] = mapped_column(String(32), nullable=False)
    ordering: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    ttl_ms: Mapped[int | None] = mapped_column(nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
