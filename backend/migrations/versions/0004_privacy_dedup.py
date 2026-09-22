"""Идемпотентность задач (jobs.dedup_key) и надгробия удалённых профилей.

Revision ID: 0004_privacy
Revises: 0003_ops
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_privacy"
down_revision: str | None = "0003_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column("jobs", sa.Column("dedup_key", sa.Text(), nullable=True))
    op.create_index(
        "ux_jobs_dedup_key",
        "jobs",
        ["dedup_key"],
        unique=True,
        postgresql_where=sa.text("dedup_key IS NOT NULL"),
    )
    op.create_table(
        "account_tombstones",
        sa.Column("max_user_key", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("max_user_key", name=op.f("pk_account_tombstones")),
    )

def downgrade() -> None:
    op.drop_table("account_tombstones")
    op.drop_index("ux_jobs_dedup_key", table_name="jobs")
    op.drop_column("jobs", "dedup_key")
