"""Фиксация набранного к началу смены кворума.

Revision ID: 0005_quorum
Revises: 0004_privacy
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_quorum"
down_revision: str | None = "0004_privacy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column("shifts", sa.Column("quorum_confirmed_at", sa.DateTime(timezone=True)))
    op.execute(
        "UPDATE shifts SET quorum_confirmed_at = starts_at WHERE quorum AND starts_at <= now()"
    )

def downgrade() -> None:
    op.drop_column("shifts", "quorum_confirmed_at")
