from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.ics import BusyEvent

DAY_START = time(8, 0)
DAY_END = time(22, 0)
MIN_FREE = timedelta(minutes=60)
OPEN_ENDED_MIN = 180

WEEKDAY_NAMES = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")

@dataclass(frozen=True)
class Window:
    starts_at: datetime
    ends_at: datetime

@dataclass(frozen=True)
class FreeSlot:
    starts_at: datetime
    ends_at: datetime
    after_label: str

def free_slots(events: Iterable[BusyEvent], tz: ZoneInfo) -> list[FreeSlot]:
    by_day: dict[date, list[BusyEvent]] = {}
    for ev in events:
        day = ev.starts_at.astimezone(tz).date()
        by_day.setdefault(day, []).append(ev)

    slots: list[FreeSlot] = []
    for day in sorted(by_day):
        day_from = datetime.combine(day, DAY_START, tzinfo=tz)
        day_to = datetime.combine(day, DAY_END, tzinfo=tz)
        day_events = sorted(by_day[day], key=lambda e: e.starts_at)
        cursor = day_from
        prev_title: str | None = None
        for ev in day_events:
            start = min(max(ev.starts_at, day_from), day_to)
            end = min(ev.ends_at, day_to)
            if start - cursor >= MIN_FREE:
                label = f"после «{prev_title}»" if prev_title else f"до «{ev.title}»"
                slots.append(FreeSlot(cursor, start, label))
            if end >= cursor:
                cursor = max(cursor, end)
                prev_title = ev.title
        if day_to - cursor >= MIN_FREE:
            label = f"после «{prev_title}»" if prev_title else "свободно весь день"
            slots.append(FreeSlot(cursor, day_to, label))
    return slots

def ceil_minutes(dt: datetime, step: int = 5) -> datetime:
    dt = dt.replace(second=0, microsecond=0) + (
        timedelta(minutes=1) if dt.second or dt.microsecond else timedelta(0)
    )
    rem = dt.minute % step
    return dt + timedelta(minutes=(step - rem) % step)

DEFAULT_EVENING = time(17, 30)
DEFAULT_WEEKEND = time(11, 0)
NOW_LEAD = timedelta(minutes=15)

def _days_for(when: str, today: date) -> list[date]:
    if when in ("now", "tonight"):
        return [today]
    if when == "tomorrow":
        return [today + timedelta(days=1)]
    wd = today.weekday()
    if wd == 6:
        return [today]
    saturday = today + timedelta(days=5 - wd)
    return [saturday, saturday + timedelta(days=1)]

def _day_start(when: str, day: date, tz: ZoneInfo, evening: time, weekend: time) -> datetime:
    return datetime.combine(day, weekend if when == "weekend" else evening, tzinfo=tz)

def window_from_slots(
    slots: Sequence[Window],
    when: str,
    duration_min: int,
    now: datetime,
    tz: ZoneInfo,
    evening: time = DEFAULT_EVENING,
    weekend: time = DEFAULT_WEEKEND,
) -> Window | None:
    need = timedelta(minutes=duration_min)
    today = now.astimezone(tz).date()
    days = set(_days_for(when, today))
    now_start = ceil_minutes(now)
    for slot in sorted(slots, key=lambda s: s.starts_at):
        day = slot.starts_at.astimezone(tz).date()
        if day not in days:
            continue
        if when == "now":
            if not (slot.starts_at <= now + NOW_LEAD and now < slot.ends_at):
                continue
            lower = now_start
        else:
            lower = max(now_start, _day_start(when, day, tz, evening, weekend))
        start = max(slot.starts_at, lower)
        if slot.ends_at - start < need:
            continue
        end = slot.ends_at if duration_min >= OPEN_ENDED_MIN else start + need
        return Window(start, end)
    return None

def next_free_window(slots: Sequence[Window], duration_min: int, now: datetime) -> Window | None:
    need = timedelta(minutes=duration_min)
    now_start = ceil_minutes(now)
    for slot in sorted(slots, key=lambda s: s.starts_at):
        start = max(slot.starts_at, now_start)
        if slot.ends_at - start >= need:
            return Window(start, slot.ends_at)
    return None

def fallback_window(
    when: str,
    duration_min: int,
    now: datetime,
    tz: ZoneInfo,
    evening: time,
    weekend: time,
) -> Window:
    local_now = now.astimezone(tz)
    today = local_now.date()
    now_start = ceil_minutes(now).astimezone(tz)
    if when == "now":
        start = now_start
    elif when == "tonight":
        start = max(now_start, datetime.combine(today, evening, tzinfo=tz))
    elif when == "tomorrow":
        start = datetime.combine(today + timedelta(days=1), evening, tzinfo=tz)
    else:
        day = _days_for("weekend", today)[0]
        start = max(now_start, datetime.combine(day, weekend, tzinfo=tz))
    return Window(start, start + timedelta(minutes=duration_min))

def intersect(windows: Iterable[Window]) -> Window | None:
    items = list(windows)
    if not items:
        return None
    start = max(w.starts_at for w in items)
    end = min(w.ends_at for w in items)
    return Window(start, end) if end > start else None

def weekday_name(dt: datetime, tz: ZoneInfo) -> str:
    return WEEKDAY_NAMES[dt.astimezone(tz).weekday()]

def hhmm(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%H:%M")
