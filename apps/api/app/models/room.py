from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UuidPrimaryKeyMixin


class RoomRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class Room(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_rooms_workspace_id_slug"),)

    workspace_id: Mapped[UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class RoomMember(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "room_members"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_room_members_room_id_user_id"),
    )

    room_id: Mapped[UUID] = mapped_column(
        ForeignKey("rooms.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class RoomReadState(UuidPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "room_read_states"
    __table_args__ = (
        UniqueConstraint("room_id", "user_id", name="uq_room_read_states_room_id_user_id"),
    )

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
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    last_read_event_seq: Mapped[int] = mapped_column(nullable=False)
