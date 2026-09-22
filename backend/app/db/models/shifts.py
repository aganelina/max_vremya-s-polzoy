import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IdMixin
from app.db.enums import (
    BOOKING_STATUS,
    CATEGORY,
    LEDGER_SOURCE,
    SHIFT_PLACE,
    SHIFT_STATUS,
    BookingStatus,
    Category,
    LedgerSource,
    ShiftPlace,
    ShiftStatus,
)


class Shift(IdMixin, CreatedAtMixin, Base):

    __tablename__ = "shifts"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="time_order"),
        CheckConstraint("capacity > 0", name="capacity_positive"),
        Index("ix_shifts_status_starts_at", "status", "starts_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    category: Mapped[Category] = mapped_column(CATEGORY, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    quorum: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    quorum_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    place: Mapped[ShiftPlace] = mapped_column(
        SHIFT_PLACE, nullable=False, server_default=ShiftPlace.ORG.value
    )
    address: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    address_note: Mapped[str | None] = mapped_column(Text)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    district_id: Mapped[str | None] = mapped_column(ForeignKey("districts.id", ondelete="SET NULL"))
    instructions: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    impact: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ShiftStatus] = mapped_column(
        SHIFT_STATUS, nullable=False, server_default=ShiftStatus.OPEN.value
    )
    checkin_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

class Booking(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index(
            "ux_bookings_active",
            "shift_id",
            "user_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
    )

    shift_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[BookingStatus] = mapped_column(
        BOOKING_STATUS, nullable=False, server_default=BookingStatus.GOING.value
    )
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL")
    )
    via_invite_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("friend_invites.id", ondelete="SET NULL")
    )
    via_transfer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("seat_transfers.id", ondelete="SET NULL", use_alter=True)
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class HourLedger(IdMixin, Base):

    __tablename__ = "hour_ledger"
    __table_args__ = (
        Index("ix_hour_ledger_user_accepted", "user_id", "accepted_at"),
        Index(
            "ux_hour_ledger_ref",
            "user_id",
            "source",
            "ref_id",
            unique=True,
            postgresql_where=text("ref_id IS NOT NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[LedgerSource] = mapped_column(LEDGER_SOURCE, nullable=False)
    ref_id: Mapped[uuid.UUID | None] = mapped_column()
    hours: Mapped[Decimal] = mapped_column(Numeric(4, 1), nullable=False)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("orgs.id", ondelete="SET NULL"))
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
