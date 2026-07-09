from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class MessageType(StrEnum):
    TEXT = "text"


class MessageSenderType(StrEnum):
    USER = "user"
    BOT = "bot"


class Message(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    room_id: Mapped[UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sender_type: Mapped[str] = mapped_column(String(32), default=MessageSenderType.USER.value)
    sender_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    sender_bot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("bots.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    reply_to_id: Mapped[UUID | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
