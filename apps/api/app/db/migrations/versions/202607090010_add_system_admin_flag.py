"""add system admin flag

Revision ID: 202607090010
Revises: 202607090009
Create Date: 2026-07-09 00:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607090010"
down_revision: str | None = "202607090009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_system_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("users", "is_system_admin", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_system_admin")
