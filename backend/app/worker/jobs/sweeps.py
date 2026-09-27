from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from sqlalchemy import Text, and_, cast, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session as db
from app.db.enums import (
    BookingStatus,
    MicroAnswerStatus,
    NotifyMode,
    ShiftStatus,
    TransferStatus,
)
from app.db.models import (
    Booking,
    BotUpdate,
    BusySlot,
    FreeWindow,
    Job,
    MicroAnswer,
    SeatTransfer,
    Shift,
    User,
)
from app.domain.hours import credit_booking
from app.worker.queue import RECOVERY_WINDOW, SCRUB_KINDS, enqueue

log = structlog.get_logger("worker")

SWEEP_INTERVAL = timedelta(minutes=1)
RETENTION = timedelta(days=90)
DONE_JOBS_RETENTION = timedelta(days=14)
BOT_UPDATES_RETENTION = timedelta(days=7)
WEEK = timedelta(days=7)
_LOCK_KEY = 0x5E_E9

async def resolve_quorums(session: AsyncSession, now: datetime) -> int:
    shifts = await session.scalars(
        select(Shift)
        .where(
            Shift.status == ShiftStatus.OPEN,
            Shift.quorum.is_(True),
            Shift.quorum_confirmed_at.is_(None),
            Shift.starts_at <= now,
        )
        .with_for_update(skip_locked=True)
    )
    cancelled = 0
    for shift in shifts:
        booked = await session.scalar(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.shift_id == shift.id,
                Booking.created_at <= shift.starts_at,
                or_(Booking.cancelled_at.is_(None), Booking.cancelled_at > shift.starts_at),
            )
        )
        if int(booked or 0) >= shift.capacity:
            shift.quorum_confirmed_at = shift.starts_at
            continue
        bookings = list(
            await session.scalars(
                select(Booking)
                .where(
                    Booking.shift_id == shift.id,
                    Booking.status.in_(
                        (BookingStatus.GOING, BookingStatus.CHECKED_IN, BookingStatus.MANUAL)
                    ),
                )
                .with_for_update()
            )
        )
        for booking in bookings:
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = now
        await session.execute(
            update(SeatTransfer)
            .where(
                SeatTransfer.booking_id.in_([b.id for b in bookings]),
                SeatTransfer.status == TransferStatus.OPEN,
            )
            .values(status=TransferStatus.EXPIRED)
        )
        shift.status = ShiftStatus.CANCELLED
        users = {str(b.user_id) for b in bookings}
        if shift.created_by:
            users.add(str(shift.created_by))
        await enqueue(
            session,
            "notify.shift_cancelled",
            {
                "shift_id": str(shift.id),
                "user_ids": sorted(users),
                "reason": "quorum",
            },
        )
        cancelled += 1
    await session.flush()
    return cancelled

async def finish_shifts(session: AsyncSession, now: datetime) -> int:
    shifts = list(
        await session.scalars(
            select(Shift)
            .where(Shift.status == ShiftStatus.OPEN, Shift.ends_at <= now)
            .with_for_update(skip_locked=True)
        )
    )
    for shift in shifts:
        came = list(
            await session.scalars(
                select(Booking).where(
                    Booking.shift_id == shift.id,
                    Booking.status.in_((BookingStatus.CHECKED_IN, BookingStatus.MANUAL)),
                )
            )
        )
        for booking in came:
            await credit_booking(session, booking, shift)
        await session.execute(
            update(Booking)
            .where(Booking.shift_id == shift.id, Booking.status == BookingStatus.GOING)
            .values(status=BookingStatus.NO_SHOW)
        )
        shift.status = ShiftStatus.FINISHED
    return len(shifts)

async def release_micro_answers(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(
        update(MicroAnswer)
        .where(MicroAnswer.status == MicroAnswerStatus.TAKEN, MicroAnswer.deadline <= now)
        .values(status=MicroAnswerStatus.RELEASED)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]

async def expire_transfers(session: AsyncSession, now: datetime) -> int:
    started = (
        select(Booking.id).join(Shift, Shift.id == Booking.shift_id).where(Shift.starts_at <= now)
    )
    result = await session.execute(
        update(SeatTransfer)
        .where(
            SeatTransfer.status == TransferStatus.OPEN,
            (SeatTransfer.expires_at <= now) | SeatTransfer.booking_id.in_(started),
        )
        .values(status=TransferStatus.EXPIRED)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]

async def end_pauses(session: AsyncSession, now: datetime) -> int:
    result = await session.execute(
        update(User)
        .where(User.notify == NotifyMode.PAUSE, User.pause_until <= now)
        .values(notify=NotifyMode.ALL, pause_until=None)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]

async def purge_old(session: AsyncSession, now: datetime) -> None:
    border = now - RETENTION
    await session.execute(delete(FreeWindow).where(FreeWindow.ends_at < border))
    await session.execute(delete(BusySlot).where(BusySlot.ends_at < border))
    await session.execute(
        delete(BotUpdate).where(BotUpdate.received_at < now - BOT_UPDATES_RETENTION)
    )
    await session.execute(delete(Job).where(Job.done_at < now - DONE_JOBS_RETENTION))
    await session.execute(
        update(Job)
        .where(
            Job.done_at < now - RECOVERY_WINDOW,
            Job.kind.in_(SCRUB_KINDS),
            Job.payload != {},
        )
        .values(payload={})
    )

_weekly_on = func.coalesce(func.jsonb_typeof(User.weekly_search), "null") == "object"

async def schedule_weekly_picks(session: AsyncSession, now: datetime) -> int:
    pending_for = Job.payload["user_id"].astext
    pending = and_(Job.kind == "notify.weekly_pick", Job.done_at.is_(None))
    await session.execute(
        update(Job)
        .where(
            pending,
            pending_for.in_(select(cast(User.id, Text)).where(~_weekly_on)),
        )
        .values(done_at=now, last_error="weekly_search_off")
    )
    has_pending = select(pending_for).where(pending)
    users = list(
        await session.scalars(
            select(User.id).where(
                _weekly_on,
                cast(User.id, Text).not_in(has_pending),
            )
        )
    )
    for user_id in users:
        await enqueue(session, "notify.weekly_pick", {"user_id": str(user_id)}, run_at=now + WEEK)
    return len(users)

@dataclass
class SweepResult:
    quorum_cancelled: int = 0
    finished: int = 0
    released: int = 0
    expired: int = 0
    unpaused: int = 0
    weekly: int = 0

async def sweep(session: AsyncSession, now: datetime) -> SweepResult | None:
    locked = await session.scalar(select(func.pg_try_advisory_xact_lock(_LOCK_KEY)))
    if not locked:
        return None
    result = SweepResult(
        quorum_cancelled=await resolve_quorums(session, now),
        finished=await finish_shifts(session, now),
        released=await release_micro_answers(session, now),
        expired=await expire_transfers(session, now),
        unpaused=await end_pauses(session, now),
        weekly=await schedule_weekly_picks(session, now),
    )
    await purge_old(session, now)
    return result

async def run_sweeps(now: datetime) -> SweepResult | None:
    async with db.transaction() as session:
        result = await sweep(session, now)
    if result is not None:
        log.info("worker_sweep", **vars(result))
    return result

class Sweeper:

    def __init__(self, interval: timedelta = SWEEP_INTERVAL) -> None:
        self._interval = interval
        self._last: datetime | None = None

    async def maybe_run(self, now: datetime) -> None:
        if self._last is not None and now - self._last < self._interval:
            return
        self._last = now
        try:
            await run_sweeps(now)
        except Exception:
            log.exception("worker_sweep_failed")
