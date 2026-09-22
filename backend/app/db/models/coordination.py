import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdMixin
from app.db.enums import (
    CERT_PERIOD,
    MESSAGE_AUDIENCE,
    RELAY_DIRECTION,
    CertPeriod,
    MessageAudience,
    RelayDirection,
)


class UrgentCall(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "urgent_calls"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    what: Mapped[str] = mapped_column(Text, nullable=False)
    where_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_in_min: Mapped[int] = mapped_column(Integer, nullable=False)
    people: Mapped[int] = mapped_column(Integer, nullable=False)
    reached: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

class UrgentRecipient(Base):
    __tablename__ = "urgent_recipients"

    call_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("urgent_calls.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Message(IdMixin, CreatedAtMixin, Base):

    __tablename__ = "messages"

    shift_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audience: Mapped[MessageAudience] = mapped_column(MESSAGE_AUDIENCE, nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

class MessageRelay(IdMixin, CreatedAtMixin, Base):

    __tablename__ = "message_relays"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    coordinator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    participant_mid: Mapped[str | None] = mapped_column(Text, index=True)
    coordinator_mid: Mapped[str | None] = mapped_column(Text, index=True)
    direction: Mapped[RelayDirection] = mapped_column(RELAY_DIRECTION, nullable=False)

class BotConversation(Base):

    __tablename__ = "bot_conversations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    relay_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("message_relays.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class Certificate(IdMixin, Base):

    __tablename__ = "certificates"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    code: Mapped[str] = mapped_column(String(7), unique=True, nullable=False)
    period: Mapped[CertPeriod] = mapped_column(CERT_PERIOD, nullable=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    total: Mapped[Decimal] = mapped_column(Numeric(6, 1), nullable=False)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
