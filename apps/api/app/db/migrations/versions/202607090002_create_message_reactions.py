"""create message reactions

Revision ID: 202607090002
Revises: 202607090001
Create Date: 2026-07-09 00:02:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090002"
down_revision: str | None = "202607090001"
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
        "message_reactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("emoji", sa.String(length=64), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_reactions_message_id_messages"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name=op.f("fk_message_reactions_room_id_rooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_message_reactions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_message_reactions_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_reactions")),
        sa.UniqueConstraint(
            "message_id",
            "user_id",
            "emoji",
            name="uq_message_reactions_message_id_user_id_emoji",
        ),
    )
    op.create_index(
        op.f("ix_message_reactions_message_id"),
        "message_reactions",
        ["message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_reactions_room_id"),
        "message_reactions",
        ["room_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_reactions_user_id"),
        "message_reactions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_message_reactions_workspace_id"),
        "message_reactions",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_message_reactions_workspace_id"), table_name="message_reactions")
    op.drop_index(op.f("ix_message_reactions_user_id"), table_name="message_reactions")
    op.drop_index(op.f("ix_message_reactions_room_id"), table_name="message_reactions")
    op.drop_index(op.f("ix_message_reactions_message_id"), table_name="message_reactions")
    op.drop_table("message_reactions")
