"""create system audit logs

Revision ID: 202607090011
Revises: 202607090010
Create Date: 2026-07-09 00:11:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090011"
down_revision: str | None = "202607090010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_system_audit_logs_actor_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_audit_logs")),
    )
    op.create_index(
        op.f("ix_system_audit_logs_action"),
        "system_audit_logs",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_audit_logs_actor_id"),
        "system_audit_logs",
        ["actor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_audit_logs_target_id"),
        "system_audit_logs",
        ["target_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_system_audit_logs_target_id"), table_name="system_audit_logs")
    op.drop_index(op.f("ix_system_audit_logs_actor_id"), table_name="system_audit_logs")
    op.drop_index(op.f("ix_system_audit_logs_action"), table_name="system_audit_logs")
    op.drop_table("system_audit_logs")
