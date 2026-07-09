"""add bot actor identity

Revision ID: 202607090004
Revises: 202607090003
Create Date: 2026-07-09 00:04:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090004"
down_revision: str | None = "202607090003"
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
        "bots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("app_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["apps.id"],
            name=op.f("fk_bots_app_id_apps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_bots_created_by_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_bots_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bots")),
        sa.UniqueConstraint("app_id", name="uq_bots_app_id"),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_bots_workspace_id_slug"),
    )
    op.create_index(op.f("ix_bots_app_id"), "bots", ["app_id"], unique=False)
    op.create_index(op.f("ix_bots_created_by_id"), "bots", ["created_by_id"], unique=False)
    op.create_index(op.f("ix_bots_workspace_id"), "bots", ["workspace_id"], unique=False)

    op.add_column(
        "messages",
        sa.Column("sender_type", sa.String(length=32), server_default="user", nullable=False),
    )
    op.add_column("messages", sa.Column("sender_bot_id", sa.Uuid(), nullable=True))
    op.alter_column("messages", "sender_id", existing_type=sa.Uuid(), nullable=True)
    op.create_foreign_key(
        op.f("fk_messages_sender_bot_id_bots"),
        "messages",
        "bots",
        ["sender_bot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_messages_sender_bot_id"), "messages", ["sender_bot_id"], unique=False)

    op.add_column(
        "events",
        sa.Column("actor_type", sa.String(length=32), server_default="user", nullable=False),
    )
    op.add_column("events", sa.Column("actor_bot_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_events_actor_bot_id_bots"),
        "events",
        "bots",
        ["actor_bot_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_events_actor_bot_id"), "events", ["actor_bot_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_events_actor_bot_id"), table_name="events")
    op.drop_constraint(op.f("fk_events_actor_bot_id_bots"), "events", type_="foreignkey")
    op.drop_column("events", "actor_bot_id")
    op.drop_column("events", "actor_type")

    op.drop_index(op.f("ix_messages_sender_bot_id"), table_name="messages")
    op.drop_constraint(op.f("fk_messages_sender_bot_id_bots"), "messages", type_="foreignkey")
    op.alter_column("messages", "sender_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("messages", "sender_bot_id")
    op.drop_column("messages", "sender_type")

    op.drop_index(op.f("ix_bots_workspace_id"), table_name="bots")
    op.drop_index(op.f("ix_bots_created_by_id"), table_name="bots")
    op.drop_index(op.f("ix_bots_app_id"), table_name="bots")
    op.drop_table("bots")
