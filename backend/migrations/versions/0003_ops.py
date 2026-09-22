"""Пульс worker для readiness-проверки (`GET /readyz`).

Revision ID: 0003_ops
Revises: 0002_b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ops"
down_revision: str | None = "0002_b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "worker_heartbeat",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_heartbeat")),
    )

def downgrade() -> None:
    op.drop_table("worker_heartbeat")
