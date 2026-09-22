"""Явный выбор и завершение личного диалога через MAX.

Revision ID: 0006_bot_conversations
Revises: 0005_quorum
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_bot_conversations"
down_revision: str | None = "0005_quorum"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.create_table(
        "bot_conversations",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("relay_id", sa.Uuid(), sa.ForeignKey("message_relays.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

def downgrade() -> None:
    op.drop_table("bot_conversations")
