import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deal_view import (
    Viewer,
    build_deals,
    busy_windows,
    load_viewer,
    open_candidates,
    study_windows,
)
from app.api.errors import NotFound, Unprocessable
from app.api.schemas.common import TimeWindow
from app.api.schemas.deals import SearchPreview, SearchResult, SearchResultItem
from app.auth.deps import DbSession, Now, OnboardedUser
from app.config import get_settings
from app.db.models import CompanyMember, FreeWindow, Org, Schedule, SearchLog, Shift, User
from app.domain import search as domain
from app.domain.participant_settings import participant_settings
from app.domain.travel import default_estimator
from app.domain.windows import (
    Window,
    fallback_window,
    intersect,
    next_free_window,
    window_from_slots,
)

router = APIRouter(tags=["search"])

STUDY_PAD = timedelta(hours=6)

async def company_window(session: AsyncSession, company_id: uuid.UUID) -> tuple[Window | None, int]:
    members = (
        await session.scalars(select(CompanyMember).where(CompanyMember.company_id == company_id))
    ).all()
    marked = [
        Window(m.window_from, m.window_to)
        for m in members
        if m.window_from is not None and m.window_to is not None
    ]
    return intersect(marked), len(marked)

WindowSource = Literal["explicit", "company", "schedule", "fallback", "none"]

@dataclass(frozen=True)
class ResolvedWindow:

    window: Window | None
    seats: int
    source: WindowSource
    next_window: Window | None = None

async def _schedule_slots(session: AsyncSession, user: User, now: datetime) -> list[Window] | None:
    if await session.get(Schedule, user.id) is None:
        return None
    slots = (
        await session.scalars(
            select(FreeWindow).where(FreeWindow.user_id == user.id, FreeWindow.ends_at > now)
        )
    ).all()
    return [Window(s.starts_at, s.ends_at) for s in slots]

async def pick_window(
    session: AsyncSession,
    user: User,
    *,
    duration_min: int,
    when: str,
    now: datetime,
    window_from: datetime | None = None,
    window_to: datetime | None = None,
    company_id: str | None = None,
) -> ResolvedWindow:
    if window_from is not None and window_to is not None:
        if window_to <= window_from:
            raise Unprocessable("bad_window")
        return ResolvedWindow(Window(window_from, window_to), 1, "explicit")
    if company_id:
        cid = _uuid(company_id)
        if cid is None or await session.get(CompanyMember, (cid, user.id)) is None:
            raise NotFound("company_not_found")
        common, marked = await company_window(session, cid)
        if common is not None:
            return ResolvedWindow(common, max(1, marked), "company")
    tz = get_settings().tz
    ps = participant_settings()
    slots = await _schedule_slots(session, user, now)
    if slots is None:
        fallback = fallback_window(
            when, duration_min, now, tz, ps.fallback_evening, ps.fallback_weekend
        )
        return ResolvedWindow(fallback, 1, "fallback")
    found = window_from_slots(
        slots, when, duration_min, now, tz, ps.fallback_evening, ps.fallback_weekend
    )
    if found is not None:
        return ResolvedWindow(found, 1, "schedule")
    return ResolvedWindow(None, 1, "none", next_free_window(slots, duration_min, now))

async def resolve_window(
    session: AsyncSession,
    user: User,
    *,
    duration_min: int,
    when: str,
    now: datetime,
    window_from: datetime | None = None,
    window_to: datetime | None = None,
    company_id: str | None = None,
) -> tuple[Window | None, int]:
    resolved = await pick_window(
        session,
        user,
        duration_min=duration_min,
        when=when,
        now=now,
        window_from=window_from,
        window_to=window_to,
        company_id=company_id,
    )
    return resolved.window, resolved.seats

def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None

async def _matches(
    session: AsyncSession,
    viewer: Viewer,
    user: User,
    window: Window,
    origin: str,
    now: datetime,
    min_seats: int,
) -> tuple[list[tuple[Shift, Org]], list[domain.Match]]:
    rows, candidates = await open_candidates(session, viewer, now, window.ends_at)
    matches = domain.search(
        candidates,
        window,
        viewer.origin(origin),
        viewer.transport,
        default_estimator(),
        await busy_windows(session, user),
        now,
        min_seats,
        await study_windows(session, user, now, window.ends_at + STUDY_PAD),
    )
    return rows, matches

async def run_search(
    session: AsyncSession,
    viewer: Viewer,
    user: User,
    window: Window | None,
    origin: str,
    now: datetime,
    min_seats: int = 1,
) -> tuple[list[SearchResultItem], dict[str, int]]:
    if window is None:
        return [], domain.counts([])
    rows, matches = await _matches(session, viewer, user, window, origin, now, min_seats)
    by_id = {s.id: (s, o) for s, o in rows}
    deals = await build_deals(
        session,
        [by_id[m.candidate.id] for m in matches],
        viewer,
        now,
        origin=origin,
        travel={m.candidate.id: m.travel_min for m in matches},
    )
    items = [
        SearchResultItem(deal=d, slack_min=m.slack_min, fit=m.fit)
        for d, m in zip(deals, matches, strict=True)
    ]
    return items, domain.counts(matches)

def _time_window(window: Window | None) -> TimeWindow | None:
    return None if window is None else TimeWindow(from_=window.starts_at, to=window.ends_at)

DURATIONS = (30, 60, 120, 180)

def check_duration(value: int) -> int:
    if value not in DURATIONS:
        raise Unprocessable("validation_error")
    return value

DurationQ = Annotated[int, Query(alias="duration_min")]
WhenQ = Annotated[Literal["now", "tonight", "tomorrow", "weekend"], Query()]
FromQ = Annotated[Literal["campus", "home"], Query(alias="from")]
CompanyQ = Annotated[str | None, Query(alias="company_id")]
WinFromQ = Annotated[AwareDatetime | None, Query(alias="window_from")]
WinToQ = Annotated[AwareDatetime | None, Query(alias="window_to")]

@router.get("/search", response_model=SearchResult)
async def search(
    user: OnboardedUser,
    session: DbSession,
    now: Now,
    duration_min: DurationQ,
    when: WhenQ,
    origin: FromQ,
    company_id: CompanyQ = None,
    window_from: WinFromQ = None,
    window_to: WinToQ = None,
) -> SearchResult:
    resolved = await pick_window(
        session,
        user,
        duration_min=check_duration(duration_min),
        when=when,
        now=now,
        window_from=window_from,
        window_to=window_to,
        company_id=company_id,
    )
    window = resolved.window
    viewer = await load_viewer(session, user)
    items, counts = await run_search(session, viewer, user, window, origin, now, resolved.seats)
    if window is not None:
        session.add(
            SearchLog(
                user_id=user.id,
                window_from=window.starts_at,
                window_to=window.ends_at,
                created_at=now,
            )
        )
        await session.commit()
    return SearchResult(
        window=_time_window(window),
        window_source=resolved.source,
        next_window=_time_window(resolved.next_window),
        items=items,
        counts=counts,
    )

@router.get("/search/preview", response_model=SearchPreview)
async def search_preview(
    user: OnboardedUser,
    session: DbSession,
    now: Now,
    duration_min: DurationQ,
    when: WhenQ,
    origin: FromQ,
    company_id: CompanyQ = None,
    window_from: WinFromQ = None,
    window_to: WinToQ = None,
) -> SearchPreview:
    window, seats = await resolve_window(
        session,
        user,
        duration_min=check_duration(duration_min),
        when=when,
        now=now,
        window_from=window_from,
        window_to=window_to,
        company_id=company_id,
    )
    if window is None:
        return SearchPreview(count=0)
    viewer = await load_viewer(session, user)
    _, matches = await _matches(session, viewer, user, window, origin, now, seats)
    return SearchPreview(count=len(matches))
