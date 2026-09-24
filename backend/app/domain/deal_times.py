from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.domain.participant_settings import participant_settings


def planned_instructions_at(starts_at: datetime, tz: ZoneInfo, hour: int) -> datetime:
    day_before = starts_at.astimezone(tz).date() - timedelta(days=1)
    return datetime.combine(day_before, time(hour), tzinfo=tz)

def instructions_at(starts_at: datetime, booked_at: datetime) -> datetime:
    settings = get_settings()
    planned = planned_instructions_at(starts_at, settings.tz, settings.instructions_hour)
    return max(planned, booked_at)

def cancel_until(starts_at: datetime) -> datetime:
    return starts_at - timedelta(hours=get_settings().cancel_hours_before)

def check_in_window(starts_at: datetime) -> tuple[datetime, datetime]:
    ps = participant_settings()
    return (
        starts_at - timedelta(minutes=ps.checkin_before_min),
        starts_at + timedelta(minutes=ps.checkin_after_min),
    )

def is_late(starts_at: datetime, checked_in_at: datetime) -> bool:
    return checked_in_at > starts_at + timedelta(minutes=participant_settings().late_after_min)
