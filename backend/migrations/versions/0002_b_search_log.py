"""Журнал поисков для метрик.

Revision ID: 0002_b
Revises: 0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_b"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "search_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("window_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_search_log_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_log")),
    )
    op.create_index("ix_search_log_created_at", "search_log", ["created_at"])
    op.create_index(op.f("ix_search_log_user_id"), "search_log", ["user_id"])

def downgrade() -> None:
    op.drop_index(op.f("ix_search_log_user_id"), table_name="search_log")
    op.drop_index("ix_search_log_created_at", table_name="search_log")
    op.drop_table("search_log")
