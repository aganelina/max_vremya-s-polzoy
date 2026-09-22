import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdMixin
from app.db.enums import TRANSFER_STATUS, TransferStatus


class FriendInvite(IdMixin, CreatedAtMixin, Base):

    __tablename__ = "friend_invites"

    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    shift_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False
    )
    inviter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

class SeatTransfer(IdMixin, CreatedAtMixin, Base):

    __tablename__ = "seat_transfers"

    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[TransferStatus] = mapped_column(
        TRANSFER_STATUS, nullable=False, server_default=TransferStatus.OPEN.value
    )
    claimed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class Company(IdMixin, CreatedAtMixin, Base):

    __tablename__ = "companies"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    picked_shift_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("shifts.id", ondelete="SET NULL")
    )

class CompanyMember(Base):
    __tablename__ = "company_members"

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    window_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

class Schedule(Base):

    __tablename__ = "schedules"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

class BusySlot(IdMixin, Base):

    __tablename__ = "busy_slots"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

class FreeWindow(IdMixin, Base):

    __tablename__ = "free_windows"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    after_label: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    place_label: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
