"""create attachments

Revision ID: 202607090001
Revises: 202607080003
Create Date: 2026-07-09 00:01:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090001"
down_revision: str | None = "202607080003"
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
        "attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("uploader_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        *timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_attachments_message_id_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["room_id"],
            ["rooms.id"],
            name=op.f("fk_attachments_room_id_rooms"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uploader_id"],
            ["users.id"],
            name=op.f("fk_attachments_uploader_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_attachments_workspace_id_workspaces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attachments")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_attachments_storage_key")),
    )
    op.create_index(op.f("ix_attachments_message_id"), "attachments", ["message_id"], unique=False)
    op.create_index(op.f("ix_attachments_room_id"), "attachments", ["room_id"], unique=False)
    op.create_index(
        op.f("ix_attachments_storage_key"),
        "attachments",
        ["storage_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attachments_uploader_id"),
        "attachments",
        ["uploader_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_attachments_workspace_id"),
        "attachments",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_attachments_workspace_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_uploader_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_storage_key"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_room_id"), table_name="attachments")
    op.drop_index(op.f("ix_attachments_message_id"), table_name="attachments")
    op.drop_table("attachments")
