"""create messages and events

Revision ID: 202607080003
Revises: 202607080002
Create Date: 2026-07-08 00:03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607080003"
down_revision: str | None = "202607080002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("sender_id", sa.Uuid(), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("reply_to_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["reply_to_id"],
            ["messages.id"],
            name=op.f("fk_messages_reply_to_id_messages"),
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name=op.f("fk_messages_room_id_rooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sender_id"],
            ["users.id"],
            name=op.f("fk_messages_sender_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_messages_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(op.f("ix_messages_room_id"), "messages", ["room_id"], unique=False)
    op.create_index(op.f("ix_messages_sender_id"), "messages", ["sender_id"], unique=False)
    op.create_index(
        op.f("ix_messages_workspace_id"),
        "messages",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("room_event_seq", sa.Integer(), nullable=True),
        sa.Column("workspace_event_seq", sa.Integer(), nullable=False),
        sa.Column("lane", sa.String(length=32), nullable=False),
        sa.Column("reliability", sa.String(length=32), nullable=False),
        sa.Column("ordering", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("ttl_ms", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_events_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name=op.f("fk_events_room_id_rooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_events_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.UniqueConstraint("room_id", "room_event_seq", name="uq_events_room_id_room_event_seq"),
        sa.UniqueConstraint(
            "workspace_id",
            "workspace_event_seq",
            name="uq_events_workspace_id_workspace_event_seq",
        ),
    )
    op.create_index(op.f("ix_events_actor_id"), "events", ["actor_id"], unique=False)
    op.create_index(
        op.f("ix_events_aggregate_id"),
        "events",
        ["aggregate_id"],
        unique=False,
    )
    op.create_index(op.f("ix_events_event_type"), "events", ["event_type"], unique=False)
    op.create_index(op.f("ix_events_room_id"), "events", ["room_id"], unique=False)
    op.create_index(op.f("ix_events_workspace_id"), "events", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_events_workspace_id"), table_name="events")
    op.drop_index(op.f("ix_events_room_id"), table_name="events")
    op.drop_index(op.f("ix_events_event_type"), table_name="events")
    op.drop_index(op.f("ix_events_aggregate_id"), table_name="events")
    op.drop_index(op.f("ix_events_actor_id"), table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_messages_workspace_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_sender_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_room_id"), table_name="messages")
    op.drop_table("messages")
