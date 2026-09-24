import asyncio
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError, Unprocessable
from app.api.schemas.deals import FreeWindow, Schedule
from app.auth.deps import DbSession, Now, OnboardedUser
from app.config import get_settings
from app.db.models import BusySlot, University, User
from app.db.models import FreeWindow as FreeWindowModel
from app.db.models import Schedule as ScheduleModel
from app.domain.ics import BusyEvent, IcsError, parse_busy
from app.domain.participant_settings import participant_settings
from app.domain.windows import FreeSlot, free_slots, hhmm, weekday_name

router = APIRouter(tags=["schedule"])

SHOW_DAYS = 7

async def build_schedule(session: AsyncSession, user: User, now: datetime) -> Schedule:
    tz = get_settings().tz
    schedule = await session.get(ScheduleModel, user.id)
    until = datetime.combine(now.astimezone(tz).date() + timedelta(days=SHOW_DAYS), time(), tz)
    rows = (
        await session.scalars(
            select(FreeWindowModel)
            .where(
                FreeWindowModel.user_id == user.id,
                FreeWindowModel.ends_at > now,
                FreeWindowModel.starts_at < until,
            )
            .order_by(FreeWindowModel.starts_at)
        )
    ).all()
    return Schedule(
        file_name=schedule.file_name if schedule else None,
        windows=[
            FreeWindow(
                id=str(w.id),
                day=weekday_name(w.starts_at, tz),
                from_=hhmm(w.starts_at, tz),
                to=hhmm(w.ends_at, tz),
                starts_at=w.starts_at,
                ends_at=w.ends_at,
                after=w.after_label,
                place=w.place_label,
            )
            for w in rows
        ],
    )

def _parse(
    text: str, tz: ZoneInfo, start: datetime, end: datetime
) -> tuple[list[BusyEvent], list[FreeSlot]]:
    events = parse_busy(text, tz, start, end)
    return events, free_slots(events, tz)

@router.get("/me/schedule", response_model=Schedule)
async def get_schedule(user: OnboardedUser, session: DbSession, now: Now) -> Schedule:
    return await build_schedule(session, user, now)

@router.post("/me/schedule", response_model=Schedule)
async def upload_schedule(
    file: UploadFile, user: OnboardedUser, session: DbSession, now: Now
) -> Schedule:
    ps = participant_settings()
    raw = await file.read(ps.schedule_max_bytes + 1)
    if len(raw) > ps.schedule_max_bytes:
        raise ApiError(413, "file_too_large")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise Unprocessable("ics_invalid") from None
    tz = get_settings().tz
    day_start = datetime.combine(now.astimezone(tz).date(), time(), tz)
    horizon = day_start + timedelta(days=ps.schedule_horizon_days)
    try:
        events, free = await asyncio.to_thread(_parse, text, tz, day_start, horizon)
    except IcsError as exc:
        code = "ics_too_large" if str(exc) in ("too_many_events", "too_complex") else "ics_invalid"
        raise Unprocessable(code) from None
    except (ValueError, OverflowError):
        raise Unprocessable("ics_invalid") from None

    university = await session.get(University, user.university_id) if user.university_id else None
    place = f"{university.name}, главный" if university else ""

    await session.execute(delete(BusySlot).where(BusySlot.user_id == user.id))
    await session.execute(delete(FreeWindowModel).where(FreeWindowModel.user_id == user.id))
    session.add_all(
        BusySlot(user_id=user.id, starts_at=e.starts_at, ends_at=e.ends_at, title=e.title[:200])
        for e in events
    )
    session.add_all(
        FreeWindowModel(
            user_id=user.id,
            starts_at=s.starts_at,
            ends_at=s.ends_at,
            after_label=s.after_label[:200],
            place_label=place,
        )
        for s in free
    )
    schedule = await session.get(ScheduleModel, user.id)
    name = (file.filename or "schedule.ics")[:200]
    if schedule is None:
        session.add(ScheduleModel(user_id=user.id, file_name=name, uploaded_at=now))
    else:
        schedule.file_name = name
        schedule.uploaded_at = now
    await session.commit()
    return await build_schedule(session, user, now)
