"""create incoming webhooks

Revision ID: 202607090005
Revises: 202607090004
Create Date: 2026-07-09 00:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090005"
down_revision: str | None = "202607090004"
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
        "incoming_webhooks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("app_id", sa.Uuid(), nullable=False),
        sa.Column("bot_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("secret_prefix", sa.String(length=24), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["app_id"],
            ["apps.id"],
            name=op.f("fk_incoming_webhooks_app_id_apps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["bot_id"],
            ["bots.id"],
            name=op.f("fk_incoming_webhooks_bot_id_bots"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_incoming_webhooks_created_by_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name=op.f("fk_incoming_webhooks_room_id_rooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_incoming_webhooks_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incoming_webhooks")),
        sa.UniqueConstraint("secret_hash", name=op.f("uq_incoming_webhooks_secret_hash")),
    )
    op.create_index(
        op.f("ix_incoming_webhooks_app_id"),
        "incoming_webhooks",
        ["app_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_incoming_webhooks_bot_id"),
        "incoming_webhooks",
        ["bot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_incoming_webhooks_created_by_id"),
        "incoming_webhooks",
        ["created_by_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_incoming_webhooks_room_id"),
        "incoming_webhooks",
        ["room_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_incoming_webhooks_secret_prefix"),
        "incoming_webhooks",
        ["secret_prefix"],
        unique=False,
    )
    op.create_index(
        op.f("ix_incoming_webhooks_workspace_id"),
        "incoming_webhooks",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_incoming_webhooks_workspace_id"), table_name="incoming_webhooks")
    op.drop_index(op.f("ix_incoming_webhooks_secret_prefix"), table_name="incoming_webhooks")
    op.drop_index(op.f("ix_incoming_webhooks_room_id"), table_name="incoming_webhooks")
    op.drop_index(op.f("ix_incoming_webhooks_created_by_id"), table_name="incoming_webhooks")
    op.drop_index(op.f("ix_incoming_webhooks_bot_id"), table_name="incoming_webhooks")
    op.drop_index(op.f("ix_incoming_webhooks_app_id"), table_name="incoming_webhooks")
    op.drop_table("incoming_webhooks")
