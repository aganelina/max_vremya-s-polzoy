import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import Date, case, delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus, LedgerSource
from app.db.models import Booking, Certificate, HourLedger, Shift
from app.worker.queue import enqueue

CREDITED_SOURCES = (LedgerSource.SHIFT, LedgerSource.MICRO)

def minutes_hours(minutes: int | float | Decimal) -> Decimal:
    return (Decimal(str(minutes)) / 60).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

def shift_hours(starts_at: datetime, ends_at: datetime) -> Decimal:
    return minutes_hours(Decimal(str((ends_at - starts_at).total_seconds())) / 60)

async def credit_booking(session: AsyncSession, booking: Booking, shift: Shift) -> None:
    booking.status = BookingStatus.DONE
    await session.execute(
        pg_insert(HourLedger)
        .values(
            user_id=booking.user_id,
            source=LedgerSource.SHIFT,
            ref_id=booking.id,
            hours=shift_hours(shift.starts_at, shift.ends_at),
            org_id=shift.org_id,
            accepted_at=shift.ends_at,
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "source", "ref_id"],
            index_where=text("ref_id IS NOT NULL"),
        )
    )
    await enqueue(session, "notify.hours_credited", {"booking_id": str(booking.id)})

async def revoke_certificates(
    session: AsyncSession, user_id: uuid.UUID, now: datetime | None = None
) -> None:
    await session.execute(
        update(Certificate)
        .where(Certificate.user_id == user_id, Certificate.revoked_at.is_(None))
        .values(revoked_at=now if now is not None else func.now())
    )

async def remove_credited(
    session: AsyncSession,
    user_id: uuid.UUID,
    source: LedgerSource,
    ref_id: uuid.UUID,
    now: datetime | None = None,
) -> bool:
    removed = (
        await session.execute(
            delete(HourLedger)
            .where(
                HourLedger.user_id == user_id,
                HourLedger.source == source,
                HourLedger.ref_id == ref_id,
            )
            .returning(HourLedger.id)
        )
    ).first()
    if removed is None:
        return False
    await revoke_certificates(session, user_id, now)
    return True

async def uncredit_booking(
    session: AsyncSession, booking: Booking, now: datetime | None = None
) -> None:
    booking.status = BookingStatus.NO_SHOW
    booking.checked_in_at = None
    await remove_credited(session, booking.user_id, LedgerSource.SHIFT, booking.id, now)

def academic_year_start(d: date) -> date:
    return date(d.year if d.month >= 9 else d.year - 1, 9, 1)

def semester_start(d: date) -> date:
    if d.month >= 9:
        return date(d.year, 9, 1)
    if d.month >= 2:
        return date(d.year, 2, 1)
    return date(d.year - 1, 9, 1)

def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())

def streak_weeks(days: Iterable[date], today: date) -> int:
    weeks = {week_start(d) for d in days}
    cursor = week_start(today)
    if cursor not in weeks:
        cursor -= timedelta(weeks=1)
    count = 0
    while cursor in weeks:
        count += 1
        cursor -= timedelta(weeks=1)
    return count

def to_hours(value: Decimal | int | float) -> float:
    return float(Decimal(value).quantize(Decimal("0.1")))

def local_midnight(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time(), tzinfo=tz)

@dataclass(frozen=True)
class UserStats:
    hours_year: float
    hours_month: float
    deals: int
    streak_weeks: int
    bank_balance: float

async def user_stats(
    session: AsyncSession, user_id: uuid.UUID, now: datetime, tz: ZoneInfo
) -> UserStats:
    today = now.astimezone(tz).date()
    year_from = local_midnight(academic_year_start(today), tz)
    month_from = local_midnight(today.replace(day=1), tz)
    credited = HourLedger.source.in_(CREDITED_SOURCES)
    zero = Decimal(0)

    hours_year, hours_month, balance = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(HourLedger.hours).filter(
                        credited, HourLedger.accepted_at >= year_from
                    ),
                    zero,
                ),
                func.coalesce(
                    func.sum(HourLedger.hours).filter(
                        credited, HourLedger.accepted_at >= month_from
                    ),
                    zero,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                HourLedger.source == LedgerSource.BANK_SPEND,
                                -func.abs(HourLedger.hours),
                            ),
                            else_=HourLedger.hours,
                        )
                    ),
                    zero,
                ),
            ).where(HourLedger.user_id == user_id)
        )
    ).one()

    local_day = func.date(func.timezone(tz.key, HourLedger.accepted_at), type_=Date)
    days: Sequence[date] = (
        await session.scalars(
            select(local_day).where(HourLedger.user_id == user_id, credited).distinct()
        )
    ).all()

    deals = await session.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.user_id == user_id, Booking.status == BookingStatus.DONE)
    )

    return UserStats(
        hours_year=to_hours(hours_year),
        hours_month=to_hours(hours_month),
        deals=int(deals or 0),
        streak_weeks=streak_weeks(days, today),
        bank_balance=to_hours(balance),
    )
