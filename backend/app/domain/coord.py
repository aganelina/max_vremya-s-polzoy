import csv
import io
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from app.api.errors import ApiError
from app.db.enums import BookingStatus
from app.domain.deal_times import is_late
from app.domain.hours import minutes_hours


class CoordError(ApiError):
    pass

TITLE_MAX = 80
DURATION_RANGE = (15, 480)
CAPACITY_RANGE = (1, 200)
URGENT_DURATION_MIN = 60
URGENT_PEOPLE_RANGE = (1, 50)
REVIEW_UNDO_WINDOW = timedelta(minutes=10)
INVITE_TTL = timedelta(days=7)
MICRO_MINUTES_RANGE = (5, 60)
MICRO_TITLE_MAX = 120
MICRO_TEXT_MAX = 1000
MESSAGE_MAX = 500

ParticipantStatus = Literal["booked", "came", "late", "no_show", "manual"]

ACTIVE_BOOKING = (
    BookingStatus.GOING,
    BookingStatus.CHECKED_IN,
    BookingStatus.MANUAL,
    BookingStatus.DONE,
    BookingStatus.NO_SHOW,
)
CAME_STATUSES = (BookingStatus.CHECKED_IN, BookingStatus.MANUAL, BookingStatus.DONE)
GOING_STATUSES = (BookingStatus.GOING, BookingStatus.CHECKED_IN, BookingStatus.MANUAL)

def local_start(day: date, at: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, at, tzinfo=tz)

def validate_new_shift(
    title: str, starts_at: datetime, duration_min: int, capacity: int, now: datetime
) -> str:
    clean = title.strip()
    if not 1 <= len(clean) <= TITLE_MAX:
        raise CoordError(422, "invalid_title")
    if not DURATION_RANGE[0] <= duration_min <= DURATION_RANGE[1]:
        raise CoordError(422, "invalid_duration")
    if not CAPACITY_RANGE[0] <= capacity <= CAPACITY_RANGE[1]:
        raise CoordError(422, "invalid_capacity")
    if starts_at <= now:
        raise CoordError(422, "starts_in_past")
    return clean

def participant_status(
    status: BookingStatus, checked_in_at: datetime | None, starts_at: datetime
) -> ParticipantStatus:
    if status is BookingStatus.MANUAL:
        return "manual"
    if status is BookingStatus.NO_SHOW:
        return "no_show"
    if status in (BookingStatus.CHECKED_IN, BookingStatus.DONE):
        if checked_in_at is not None and is_late(starts_at, checked_in_at):
            return "late"
        return "came"
    return "booked"

def recipient_limit(people: int) -> int:
    return min(40, max(15, people * 3))

@dataclass(frozen=True)
class UrgentCandidate:
    user_id: uuid.UUID
    has_window: bool
    near_district: bool
    near_campus: bool

def pick_recipients(candidates: Iterable[UrgentCandidate], limit: int) -> list[UrgentCandidate]:

    def rank(c: UrgentCandidate) -> int:
        if c.has_window:
            return 0
        if c.near_district or c.near_campus:
            return 1
        return 2

    ranked = sorted((c for c in candidates if rank(c) < 2), key=rank)
    return ranked[:limit]

def micro_hours(minutes: int) -> Decimal:
    return minutes_hours(minutes)

def can_undo_review(reviewed_at: datetime | None, now: datetime) -> bool:
    return reviewed_at is not None and now - reviewed_at <= REVIEW_UNDO_WINDOW

CSV_HEADER = ("date", "shift", "name", "status", "checked_in_at", "hours")

@dataclass(frozen=True)
class CsvRow:
    starts_at: datetime
    shift: str
    name: str
    status: ParticipantStatus
    checked_in_at: datetime | None
    hours: Decimal | None

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")

def csv_safe(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_START) else value

def attendance_csv(rows: Sequence[CsvRow], tz: ZoneInfo) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(
            (
                row.starts_at.astimezone(tz).date().isoformat(),
                csv_safe(row.shift),
                csv_safe(row.name),
                row.status,
                row.checked_in_at.astimezone(tz).isoformat(timespec="minutes")
                if row.checked_in_at
                else "",
                f"{row.hours:.1f}" if row.hours is not None else "",
            )
        )
    return "﻿" + buf.getvalue()
