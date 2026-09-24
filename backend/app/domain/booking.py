import uuid
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import Conflict, NotFound
from app.db.enums import BookingStatus, OrgStatus, ShiftStatus
from app.db.models import Booking, Org, Shift, User
from app.domain.deal_times import instructions_at
from app.domain.mentorship import create_mentor_requests_for_booking
from app.domain.search import overlaps
from app.worker.queue import enqueue

ACTIVE = (BookingStatus.GOING, BookingStatus.CHECKED_IN, BookingStatus.MANUAL)

def user_lock_key(user_id: uuid.UUID) -> int:
    return int.from_bytes(user_id.bytes[:8], "big", signed=True)

async def lock_user_bookings(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": user_lock_key(user_id)}
    )

async def lock_shift(session: AsyncSession, shift_id: uuid.UUID) -> tuple[Shift, Org]:
    row = (
        await session.execute(
            select(Shift, Org)
            .join(Org, Org.id == Shift.org_id)
            .where(Shift.id == shift_id)
            .with_for_update(of=Shift)
        )
    ).first()
    if row is None:
        raise NotFound("deal_not_found")
    return row[0], row[1]

async def active_booking(
    session: AsyncSession, user_id: uuid.UUID, shift_id: uuid.UUID
) -> Booking | None:
    return await session.scalar(
        select(Booking).where(
            Booking.user_id == user_id,
            Booking.shift_id == shift_id,
            Booking.status != BookingStatus.CANCELLED,
        )
    )

def ensure_bookable(shift: Shift, org: Org, now: datetime) -> None:
    if shift.status is not ShiftStatus.OPEN or org.status is not OrgStatus.VERIFIED:
        raise Conflict("deal_closed")
    if shift.starts_at <= now:
        raise Conflict("deal_closed")

async def seats_taken(session: AsyncSession, shift_id: uuid.UUID) -> int:
    n = await session.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.shift_id == shift_id, Booking.status != BookingStatus.CANCELLED)
    )
    return int(n or 0)

async def has_time_conflict(
    session: AsyncSession, user_id: uuid.UUID, shift: Shift, extra: list[Shift] | None = None
) -> bool:
    rows = await session.execute(
        select(Shift.starts_at, Shift.ends_at)
        .join(Booking, Booking.shift_id == Shift.id)
        .where(
            Booking.user_id == user_id,
            Booking.status.in_(ACTIVE),
            Shift.id != shift.id,
        )
    )
    intervals = [(s, e) for s, e in rows]
    intervals += [(o.starts_at, o.ends_at) for o in extra or [] if o.id != shift.id]
    return any(overlaps(shift.starts_at, shift.ends_at, s, e) for s, e in intervals)

async def schedule_instructions(
    session: AsyncSession, booking: Booking, shift: Shift, now: datetime
) -> None:
    await enqueue(
        session,
        "notify.instructions",
        {"booking_id": str(booking.id)},
        run_at=instructions_at(shift.starts_at, now),
    )

async def create_booking(
    session: AsyncSession,
    user: User,
    shift_id: uuid.UUID,
    now: datetime,
    *,
    company_id: uuid.UUID | None = None,
    via_invite_id: uuid.UUID | None = None,
    via_transfer_id: uuid.UUID | None = None,
    reserved_seat: bool = False,
    extra_busy: list[Shift] | None = None,
) -> tuple[Booking, bool]:
    await lock_user_bookings(session, user.id)
    shift, org = await lock_shift(session, shift_id)
    existing = await active_booking(session, user.id, shift.id)
    if existing is not None:
        return existing, False
    ensure_bookable(shift, org, now)
    if not reserved_seat and await seats_taken(session, shift.id) >= shift.capacity:
        raise Conflict("seat_taken")
    if await has_time_conflict(session, user.id, shift, extra_busy):
        raise Conflict("time_conflict")
    booking = Booking(
        shift_id=shift.id,
        user_id=user.id,
        status=BookingStatus.GOING,
        company_id=company_id,
        via_invite_id=via_invite_id,
        via_transfer_id=via_transfer_id,
        created_at=now,
    )
    session.add(booking)
    await session.flush()
    await schedule_instructions(session, booking, shift, now)
    await create_mentor_requests_for_booking(session, booking)
    return booking, True
