"""create user contacts

Revision ID: 202607100002
Revises: 202607100001
Create Date: 2026-07-10 10:02:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607100002"
down_revision: str | None = "202607100001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("contact_user_id", sa.Uuid(), nullable=False),
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
            ["contact_user_id"],
            ["users.id"],
            name=op.f("fk_user_contacts_contact_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_user_contacts_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_contacts")),
        sa.UniqueConstraint(
            "owner_user_id",
            "contact_user_id",
            name="uq_user_contacts_owner_contact",
        ),
    )
    op.create_index(op.f("ix_user_contacts_contact_user_id"), "user_contacts", ["contact_user_id"])
    op.create_index(op.f("ix_user_contacts_owner_user_id"), "user_contacts", ["owner_user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_user_contacts_owner_user_id"), table_name="user_contacts")
    op.drop_index(op.f("ix_user_contacts_contact_user_id"), table_name="user_contacts")
    op.drop_table("user_contacts")
