import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.db.enums import Category, Transport
from app.domain.travel import Point, TravelEstimator
from app.domain.windows import Window

TIGHT_SLACK_MIN = 5
NEAR_TRAVEL_MIN = 10
ROUTE_MAX_WALK_MIN = 15
ROUTE_MIN_GAP_MIN = 3

@dataclass(frozen=True)
class Candidate:
    id: uuid.UUID
    category: Category
    starts_at: datetime
    ends_at: datetime
    point: Point | None
    district_id: str | None
    online: bool
    seats_left: int
    booked_by_me: bool = False

    @property
    def minutes(self) -> int:
        return int((self.ends_at - self.starts_at).total_seconds() // 60)

@dataclass(frozen=True)
class Origin:

    kind: str
    point: Point | None = None
    home_district: str | None = None
    districts: frozenset[str] = frozenset()

    @property
    def is_home(self) -> bool:
        return self.kind == "home"

@dataclass(frozen=True)
class Match:
    candidate: Candidate
    travel_min: int | None
    slack_min: int
    fit: str
    near: bool

def _minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)

def travel_between(
    a: Point | None, b: Point | None, transport: Transport, estimator: TravelEstimator
) -> int | None:
    if a is None or b is None:
        return None
    return estimator.minutes(a, b, transport)

def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end

def conflicts(c: Candidate, busy: Iterable[Window]) -> bool:
    return any(overlaps(c.starts_at, c.ends_at, w.starts_at, w.ends_at) for w in busy)

def blocked_by_study(c: Candidate, road: int, study: Iterable[Window]) -> bool:
    pad = timedelta(minutes=road)
    return any(overlaps(c.starts_at - pad, c.ends_at + pad, w.starts_at, w.ends_at) for w in study)

def travel_for(
    c: Candidate, origin: Origin, transport: Transport, estimator: TravelEstimator
) -> int | None:
    if c.online:
        return 0
    if origin.is_home:
        return None
    return travel_between(origin.point, c.point, transport, estimator)

def match(
    c: Candidate,
    window: Window,
    origin: Origin,
    transport: Transport,
    estimator: TravelEstimator,
    busy: Sequence[Window] = (),
    now: datetime | None = None,
    min_seats: int = 1,
    study: Sequence[Window] = (),
) -> Match | None:
    if now is not None and c.starts_at <= now:
        return None
    if not c.booked_by_me and c.seats_left < min_seats:
        return None
    if not c.booked_by_me and conflicts(c, busy):
        return None
    if origin.is_home and not c.online and c.district_id not in origin.districts:
        return None
    travel = travel_for(c, origin, transport, estimator)
    if travel is None and not origin.is_home:
        return None
    road = travel or 0
    if not c.booked_by_me and blocked_by_study(c, road, study):
        return None
    before = _minutes(c.starts_at - window.starts_at) - road
    after = _minutes(window.ends_at - c.ends_at) - road
    if before < 0 or after < 0:
        return None
    slack = min(before, after)
    if origin.is_home:
        near = c.online or c.district_id == origin.home_district
    else:
        near = travel is not None and travel <= NEAR_TRAVEL_MIN
    return Match(
        candidate=c,
        travel_min=travel,
        slack_min=slack,
        fit="tight" if slack <= TIGHT_SLACK_MIN else "ok",
        near=near,
    )

def search(
    candidates: Iterable[Candidate],
    window: Window,
    origin: Origin,
    transport: Transport,
    estimator: TravelEstimator,
    busy: Sequence[Window] = (),
    now: datetime | None = None,
    min_seats: int = 1,
    study: Sequence[Window] = (),
) -> list[Match]:
    found = [
        m
        for c in candidates
        if (m := match(c, window, origin, transport, estimator, busy, now, min_seats, study))
    ]
    found.sort(key=lambda m: (m.candidate.starts_at, m.travel_min or 0, str(m.candidate.id)))
    return found

def counts(matches: Sequence[Match]) -> dict[str, int]:
    result = {"all": len(matches), "near": sum(1 for m in matches if m.near)}
    for cat in Category:
        result[cat.value] = sum(1 for m in matches if m.candidate.category is cat)
    return result

@dataclass(frozen=True)
class RoutePlan:
    first: Candidate
    second: Candidate
    walk_min: int
    travel_first: int | None
    travel_second: int | None

def best_route(
    candidates: Sequence[Candidate],
    window: Window,
    origin: Origin,
    transport: Transport,
    estimator: TravelEstimator,
    busy: Sequence[Window] = (),
    now: datetime | None = None,
    max_walk: int = ROUTE_MAX_WALK_MIN,
    min_gap: int = ROUTE_MIN_GAP_MIN,
    study: Sequence[Window] = (),
) -> RoutePlan | None:
    usable = [
        c
        for c in candidates
        if not c.booked_by_me
        and c.seats_left > 0
        and not conflicts(c, busy)
        and (now is None or c.starts_at > now)
        and (not origin.is_home or c.online or c.district_id in origin.districts)
    ]
    reach: dict[uuid.UUID, int | None] = {}
    for c in usable:
        travel = travel_for(c, origin, transport, estimator)
        if travel is None and not origin.is_home:
            continue
        if blocked_by_study(c, travel or 0, study):
            continue
        reach[c.id] = travel
    usable = [c for c in usable if c.id in reach]
    best: tuple[tuple[int, float, int], RoutePlan] | None = None
    for a in usable:
        travel_a = reach[a.id]
        if _minutes(a.starts_at - window.starts_at) - (travel_a or 0) < 0:
            continue
        for b in usable:
            if b.id == a.id or b.starts_at < a.ends_at:
                continue
            if a.online or b.online:
                walk: int | None = 0
            else:
                walk = travel_between(a.point, b.point, transport, estimator)
            if walk is None or walk > max_walk:
                continue
            if _minutes(b.starts_at - a.ends_at) - walk < min_gap:
                continue
            travel_b = reach[b.id]
            if _minutes(window.ends_at - b.ends_at) - (travel_b or 0) < 0:
                continue
            score = (a.minutes + b.minutes, -a.starts_at.timestamp(), -walk)
            if best is None or score > best[0]:
                best = (score, RoutePlan(a, b, walk, travel_a, travel_b))
    return best[1] if best else None
