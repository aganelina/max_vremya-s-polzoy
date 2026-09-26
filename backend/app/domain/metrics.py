import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.enums import BookingStatus, LedgerSource, OrgStatus, ShiftStatus
from app.db.models import (
    Booking,
    CompanyMember,
    HourLedger,
    Org,
    Schedule,
    SearchLog,
    Shift,
)
from app.domain.coord import CAME_STATUSES
from app.domain.hours import CREDITED_SOURCES, to_hours

PERIOD = timedelta(weeks=6)
MIN_GROUP = 3
PERIOD_LABEL = "Пилот · за 6 недель"
PILOT_AVERAGE = "В среднем по пилоту"

_SETTLED = (*CAME_STATUSES, BookingStatus.NO_SHOW, BookingStatus.GOING)

@dataclass(frozen=True)
class OrgRow:
    org_id: uuid.UUID
    name: str
    people: int
    came: int
    settled: int
    hours: Decimal

    @property
    def attendance(self) -> float:
        return round(self.came / self.settled, 2) if self.settled else 0.0

@dataclass(frozen=True)
class FunnelStep:
    label: str
    value: int
    note: str

@dataclass(frozen=True)
class OrgLine:
    name: str
    attendance: float
    hours: float

@dataclass(frozen=True)
class MetricsView:
    period_label: str
    hours: float
    participants: int
    returned_share: float
    funnel: list[FunnelStep]
    orgs: list[OrgLine]

def share(part: int, whole: int) -> int:
    return round(part * 100 / whole) if whole else 0

def funnel(windows: int, booked: int, came: int) -> list[FunnelStep]:
    steps = [
        FunnelStep("Указали окно", windows, "все, кто искал дело"),
        FunnelStep("Записались", booked, f"{share(booked, windows)}% от окон"),
        FunnelStep("Пришли", came, f"{share(came, booked)}% от записей"),
    ]
    return [
        s if s.value >= MIN_GROUP else FunnelStep(s.label, 0, "меньше 3 человек") for s in steps
    ]

def visible(rows: Iterable[OrgRow]) -> list[OrgRow]:
    return [r for r in rows if r.people >= MIN_GROUP]

def pilot_average(rows: Sequence[OrgRow]) -> OrgLine | None:
    shown = visible(rows)
    if not shown:
        return None
    return OrgLine(
        name=PILOT_AVERAGE,
        attendance=round(sum(r.attendance for r in shown) / len(shown), 2),
        hours=to_hours(sum((r.hours for r in shown), Decimal(0)) / len(shown)),
    )

def org_lines(rows: Sequence[OrgRow], own_org_id: uuid.UUID | None) -> list[OrgLine]:
    shown = visible(rows)
    if own_org_id is not None:
        shown = [r for r in shown if r.org_id == own_org_id]
    lines = [
        OrgLine(r.name, r.attendance, to_hours(r.hours))
        for r in sorted(shown, key=lambda r: r.hours, reverse=True)
    ]
    avg = pilot_average(rows)
    if avg is not None:
        lines.append(avg)
    return lines

async def _user_set(session: AsyncSession, stmt: Select[Any]) -> set[uuid.UUID]:
    return set(await session.scalars(stmt))

async def org_rows(session: AsyncSession, since: datetime, now: datetime) -> list[OrgRow]:
    late_cancel = (
        (Booking.status == BookingStatus.CANCELLED)
        & (Shift.status != ShiftStatus.CANCELLED)
        & (
            Booking.cancelled_at
            > Shift.starts_at - timedelta(hours=get_settings().cancel_hours_before)
        )
    )
    people_stmt = (
        select(
            Shift.org_id,
            func.count(func.distinct(Booking.user_id)),
            func.count().filter(Booking.status.in_(CAME_STATUSES)),
            func.count(),
        )
        .join(Shift, Shift.id == Booking.shift_id)
        .where(
            Shift.starts_at >= since,
            Shift.ends_at <= now,
            Booking.status.in_(_SETTLED) | late_cancel,
        )
        .group_by(Shift.org_id)
    )
    counts = {row[0]: (row[1], row[2], row[3]) for row in await session.execute(people_stmt)}
    hours_stmt = (
        select(HourLedger.org_id, func.sum(HourLedger.hours))
        .where(
            HourLedger.source.in_(CREDITED_SOURCES),
            HourLedger.accepted_at >= since,
            HourLedger.accepted_at <= now,
            HourLedger.org_id.is_not(None),
        )
        .group_by(HourLedger.org_id)
    )
    hours = {row[0]: Decimal(row[1]) for row in await session.execute(hours_stmt)}
    orgs = await session.execute(select(Org.id, Org.name).where(Org.status == OrgStatus.VERIFIED))
    rows = []
    for org_id, name in orgs:
        people, came, settled = counts.get(org_id, (0, 0, 0))
        if not settled and org_id not in hours:
            continue
        rows.append(OrgRow(org_id, name, people, came, settled, hours.get(org_id, Decimal(0))))
    return rows

async def compute_metrics(
    session: AsyncSession, now: datetime, own_org_id: uuid.UUID | None
) -> MetricsView:
    since = now - PERIOD
    booked = await _user_set(
        session,
        select(Booking.user_id).where(Booking.created_at >= since, Booking.created_at <= now),
    )
    windows = booked | await _user_set(
        session, select(Schedule.user_id).where(Schedule.uploaded_at >= since)
    )
    windows |= await _user_set(
        session,
        select(SearchLog.user_id).where(SearchLog.created_at >= since, SearchLog.created_at <= now),
    )
    windows |= await _user_set(
        session,
        select(CompanyMember.user_id).where(
            CompanyMember.window_from.is_not(None), CompanyMember.joined_at >= since
        ),
    )
    came = await _user_set(
        session,
        select(Booking.user_id)
        .join(Shift, Shift.id == Booking.shift_id)
        .where(
            Booking.status.in_(CAME_STATUSES),
            Shift.starts_at >= since,
            Shift.starts_at <= now,
        ),
    )
    credited_filter = (
        HourLedger.source.in_(CREDITED_SOURCES),
        HourLedger.accepted_at >= since,
        HourLedger.accepted_at <= now,
    )
    participants = came | await _user_set(
        session, select(HourLedger.user_id).where(*credited_filter)
    )
    total = await session.scalar(
        select(func.coalesce(func.sum(HourLedger.hours), 0)).where(*credited_filter)
    )
    returned = 0
    if participants:
        activity = await session.execute(
            select(HourLedger.user_id, func.count())
            .where(
                HourLedger.user_id.in_(participants),
                HourLedger.source.in_((LedgerSource.SHIFT, LedgerSource.MICRO)),
                HourLedger.accepted_at <= now,
            )
            .group_by(HourLedger.user_id)
        )
        returned = sum(1 for _, n in activity if n >= 2)

    small = len(participants) < MIN_GROUP
    rows = await org_rows(session, since, now)
    return MetricsView(
        period_label=PERIOD_LABEL,
        hours=0.0 if small else to_hours(Decimal(total or 0)),
        participants=0 if small else len(participants),
        returned_share=0.0 if small else round(returned / len(participants), 2),
        funnel=funnel(len(windows), len(booked), len(came)),
        orgs=org_lines(rows, own_org_id),
    )
