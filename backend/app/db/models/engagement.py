import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdMixin
from app.db.enums import (
    HELP_STATUS,
    MENTOR_REQUEST_STATUS,
    MICRO_ANSWER_STATUS,
    HelpStatus,
    MentorRequestStatus,
    MicroAnswerStatus,
)


class MicroTask(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "micro_tasks"
    __table_args__ = (
        CheckConstraint("minutes BETWEEN 5 AND 60", name="minutes_range"),
        CheckConstraint("answers_needed > 0", name="answers_needed_positive"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    text: Mapped[str] = mapped_column(String(1000), nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    answers_needed: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

class MicroAnswer(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "micro_answers"
    __table_args__ = (
        Index(
            "ux_micro_answers_one_taken",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'taken'"),
        ),
    )

    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("micro_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[MicroAnswerStatus] = mapped_column(MICRO_ANSWER_STATUS, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class HelpRequest(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "help_requests"
    __table_args__ = (CheckConstraint("hours > 0", name="hours_positive"),)

    author_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(3, 1), nullable=False)
    when_label: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    district_id: Mapped[str | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"))
    status: Mapped[HelpStatus] = mapped_column(
        HELP_STATUS, nullable=False, server_default=HelpStatus.OPEN.value
    )
    helper_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

class HelpResponse(Base):
    __tablename__ = "help_responses"

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("help_requests.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

class MentorSettings(Base):
    __tablename__ = "mentor_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    accepting: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

class MentorRequest(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "mentor_requests"

    newbie_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shift_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    mentor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[MentorRequestStatus] = mapped_column(
        MENTOR_REQUEST_STATUS, nullable=False, server_default=MentorRequestStatus.OPEN.value
    )
