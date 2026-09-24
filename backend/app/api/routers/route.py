from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response

from app.api.deal_view import (
    build_deals,
    busy_windows,
    load_viewer,
    open_candidates,
    parse_uuid,
    study_windows,
)
from app.api.errors import NotFound
from app.api.routers.search import STUDY_PAD, check_duration, resolve_window
from app.api.schemas.common import TimeWindow
from app.api.schemas.deals import Route, RouteBookIn, RouteLeg
from app.auth.deps import DbSession, Now, OnboardedUser
from app.domain.booking import create_booking, lock_shift, lock_user_bookings
from app.domain.search import best_route
from app.domain.travel import default_estimator

router = APIRouter(tags=["route"])

@router.get("/route", response_model=Route)
async def get_route(
    user: OnboardedUser,
    session: DbSession,
    now: Now,
    duration_min: Annotated[int, Query(alias="duration_min")] = 180,
    when: Annotated[Literal["now", "tonight", "tomorrow", "weekend"], Query()] = "tonight",
    origin: Annotated[Literal["campus", "home"], Query(alias="from")] = "campus",
) -> Route:
    window, _ = await resolve_window(
        session, user, duration_min=check_duration(duration_min), when=when, now=now
    )
    if window is None:
        raise NotFound("no_route")
    viewer = await load_viewer(session, user)
    rows, candidates = await open_candidates(session, viewer, now, window.ends_at)
    plan = best_route(
        candidates,
        window,
        viewer.origin(origin),
        viewer.transport,
        default_estimator(),
        await busy_windows(session, user),
        now,
        study=await study_windows(session, user, now, window.ends_at + STUDY_PAD),
    )
    if plan is None:
        raise NotFound("no_route")
    by_id = {s.id: (s, o) for s, o in rows}
    first, second = await build_deals(
        session,
        [by_id[plan.first.id], by_id[plan.second.id]],
        viewer,
        now,
        origin=origin,
        travel={plan.first.id: plan.travel_first, plan.second.id: plan.travel_second},
    )
    return Route(
        window=TimeWindow(from_=window.starts_at, to=window.ends_at),
        legs=[
            RouteLeg(deal=first, walk_to_next_min=plan.walk_min),
            RouteLeg(deal=second, walk_to_next_min=None),
        ],
    )

@router.post("/route/bookings", status_code=204)
async def book_route(
    body: RouteBookIn, user: OnboardedUser, session: DbSession, now: Now
) -> Response:
    """Всё или ничего: любая ошибка (seat_taken, time_conflict) откатывает все записи."""
    ids = []
    for raw in dict.fromkeys(body.deal_ids):
        sid = parse_uuid(raw)
        if sid is None:
            raise NotFound("deal_not_found")
        ids.append(sid)
    await lock_user_bookings(session, user.id)
    shifts = [(await lock_shift(session, sid))[0] for sid in sorted(ids)]
    for shift in shifts:
        others = [s for s in shifts if s.id != shift.id]
        await create_booking(session, user, shift.id, now, extra_busy=others)
    await session.commit()
    return Response(status_code=204)
