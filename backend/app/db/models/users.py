import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdMixin
from app.db.enums import NOTIFY_MODE, TRANSPORT, NotifyMode, Transport


class User(IdMixin, CreatedAtMixin, Base):

    __tablename__ = "users"

    max_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    is_operator: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    university_id: Mapped[str | None] = mapped_column(
        ForeignKey("universities.id", ondelete="SET NULL")
    )
    district_id: Mapped[str | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"))
    interests: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    transport: Mapped[Transport] = mapped_column(
        TRANSPORT, nullable=False, server_default=Transport.WALK.value
    )
    notify: Mapped[NotifyMode] = mapped_column(
        NOTIFY_MODE, nullable=False, server_default=NotifyMode.ALL.value
    )
    pause_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    weekly_search: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

class MaxChat(Base):

    __tablename__ = "max_chats"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
