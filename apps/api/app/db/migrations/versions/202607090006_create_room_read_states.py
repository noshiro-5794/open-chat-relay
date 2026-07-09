"""create room read states

Revision ID: 202607090006
Revises: 202607090005
Create Date: 2026-07-09 00:06:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090006"
down_revision: str | None = "202607090005"
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
        "room_read_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_read_event_seq", sa.Integer(), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name=op.f("fk_room_read_states_room_id_rooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_room_read_states_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_room_read_states_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_room_read_states")),
        sa.UniqueConstraint(
            "room_id",
            "user_id",
            name="uq_room_read_states_room_id_user_id",
        ),
    )
    op.create_index(
        op.f("ix_room_read_states_room_id"),
        "room_read_states",
        ["room_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_room_read_states_user_id"),
        "room_read_states",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_room_read_states_workspace_id"),
        "room_read_states",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_room_read_states_workspace_id"), table_name="room_read_states")
    op.drop_index(op.f("ix_room_read_states_user_id"), table_name="room_read_states")
    op.drop_index(op.f("ix_room_read_states_room_id"), table_name="room_read_states")
    op.drop_table("room_read_states")
