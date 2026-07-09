"""create event outbox

Revision ID: 202607090008
Revises: 202607090007
Create Date: 2026-07-09 00:08:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090008"
down_revision: str | None = "202607090007"
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
        "event_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_event_outbox_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name=op.f("fk_event_outbox_room_id_rooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_event_outbox_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_outbox")),
        sa.UniqueConstraint("event_id", name=op.f("uq_event_outbox_event_id")),
    )
    op.create_index(op.f("ix_event_outbox_event_id"), "event_outbox", ["event_id"], unique=True)
    op.create_index(op.f("ix_event_outbox_room_id"), "event_outbox", ["room_id"], unique=False)
    op.create_index(op.f("ix_event_outbox_status"), "event_outbox", ["status"], unique=False)
    op.create_index(
        op.f("ix_event_outbox_workspace_id"),
        "event_outbox",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_event_outbox_workspace_id"), table_name="event_outbox")
    op.drop_index(op.f("ix_event_outbox_status"), table_name="event_outbox")
    op.drop_index(op.f("ix_event_outbox_room_id"), table_name="event_outbox")
    op.drop_index(op.f("ix_event_outbox_event_id"), table_name="event_outbox")
    op.drop_table("event_outbox")
