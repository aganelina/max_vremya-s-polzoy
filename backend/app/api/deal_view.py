import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.deals import Booking as BookingOut
from app.api.schemas.deals import Deal, Org
from app.db.enums import BookingStatus, OrgStatus, ShiftPlace, ShiftStatus, Transport
from app.db.models import Booking, BusySlot, DistrictAdjacency, Shift, University, User
from app.db.models import Org as OrgModel
from app.domain.deal_times import cancel_until, check_in_window, instructions_at
from app.domain.hours import shift_hours
from app.domain.search import Candidate, Origin, travel_for
from app.domain.travel import Point, TravelEstimator, default_estimator
from app.domain.windows import Window

ACTIVE = (BookingStatus.GOING, BookingStatus.CHECKED_IN, BookingStatus.MANUAL)
NOT_CANCELLED = Booking.status != BookingStatus.CANCELLED

def booking_out(b: Booking) -> BookingOut:
    return BookingOut(
        id=str(b.id),
        deal_id=str(b.shift_id),
        status=b.status.value,
        checked_in_at=b.checked_in_at,
    )

@dataclass
class Viewer:
    user: User | None
    transport: Transport
    campus: Point | None
    home_district: str | None
    districts: frozenset[str]

    def origin(self, kind: str) -> Origin:
        if kind == "home":
            return Origin(kind="home", home_district=self.home_district, districts=self.districts)
        return Origin(kind="campus", point=self.campus)

async def load_viewer(session: AsyncSession, user: User | None) -> Viewer:
    campus = None
    districts: set[str] = set()
    if user is not None and user.university_id:
        uni = await session.get(University, user.university_id)
        if uni is not None:
            campus = Point(uni.lat, uni.lon)
    if user is not None and user.district_id:
        districts.add(user.district_id)
        districts.update(
            await session.scalars(
                select(DistrictAdjacency.neighbor_id).where(
                    DistrictAdjacency.district_id == user.district_id
                )
            )
        )
    return Viewer(
        user=user,
        transport=user.transport if user is not None else Transport.WALK,
        campus=campus,
        home_district=user.district_id if user is not None else None,
        districts=frozenset(districts),
    )

def shift_point(shift: Shift, org: OrgModel) -> Point | None:
    if shift.place is ShiftPlace.ONLINE:
        return None
    if shift.lat is not None and shift.lon is not None:
        return Point(shift.lat, shift.lon)
    if org.lat is not None and org.lon is not None:
        return Point(org.lat, org.lon)
    return None

def shift_district(shift: Shift, org: OrgModel) -> str | None:
    return shift.district_id or org.district_id

def candidate(shift: Shift, org: OrgModel, taken: int, booked_by_me: bool) -> Candidate:
    return Candidate(
        id=shift.id,
        category=shift.category,
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
        point=shift_point(shift, org),
        district_id=shift_district(shift, org),
        online=shift.place is ShiftPlace.ONLINE,
        seats_left=shift.capacity - taken,
        booked_by_me=booked_by_me,
    )

async def taken_counts(
    session: AsyncSession, shift_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not shift_ids:
        return {}
    rows = await session.execute(
        select(Booking.shift_id, func.count())
        .where(Booking.shift_id.in_(shift_ids), NOT_CANCELLED)
        .group_by(Booking.shift_id)
    )
    return {sid: int(n) for sid, n in rows}

async def my_bookings(
    session: AsyncSession, user: User | None, shift_ids: Sequence[uuid.UUID] | None = None
) -> dict[uuid.UUID, Booking]:
    if user is None:
        return {}
    q = select(Booking).where(Booking.user_id == user.id, NOT_CANCELLED)
    if shift_ids is not None:
        q = q.where(Booking.shift_id.in_(shift_ids))
    return {b.shift_id: b for b in await session.scalars(q)}

async def busy_windows(
    session: AsyncSession, user: User, exclude: Sequence[uuid.UUID] = ()
) -> list[Window]:
    q = (
        select(Shift.id, Shift.starts_at, Shift.ends_at)
        .join(Booking, Booking.shift_id == Shift.id)
        .where(Booking.user_id == user.id, Booking.status.in_(ACTIVE))
    )
    return [Window(s, e) for sid, s, e in (await session.execute(q)) if sid not in exclude]

async def study_windows(
    session: AsyncSession, user: User, since: datetime, until: datetime
) -> list[Window]:
    q = select(BusySlot.starts_at, BusySlot.ends_at).where(
        BusySlot.user_id == user.id, BusySlot.ends_at > since, BusySlot.starts_at < until
    )
    return [Window(s, e) for s, e in await session.execute(q)]

async def build_deals(
    session: AsyncSession,
    rows: Sequence[tuple[Shift, OrgModel]],
    viewer: Viewer,
    now: datetime,
    *,
    origin: str = "campus",
    travel: dict[uuid.UUID, int | None] | None = None,
    estimator: TravelEstimator | None = None,
) -> list[Deal]:
    if not rows:
        return []
    estimator = estimator or default_estimator()
    ids = [s.id for s, _ in rows]
    taken = await taken_counts(session, ids)
    mine = await my_bookings(session, viewer.user, ids)
    initials: dict[uuid.UUID, list[str]] = {}
    q = (
        select(Booking.shift_id, User.first_name)
        .join(User, User.id == Booking.user_id)
        .where(Booking.shift_id.in_(ids), NOT_CANCELLED)
        .order_by(Booking.created_at, Booking.id)
    )
    if viewer.user is not None:
        q = q.where(Booking.user_id != viewer.user.id)
    for sid, name in await session.execute(q):
        if name:
            initials.setdefault(sid, []).append(name[0].upper())

    deals: list[Deal] = []
    for shift, org in rows:
        if travel is not None and shift.id in travel:
            minutes = travel[shift.id]
        else:
            c = candidate(shift, org, taken.get(shift.id, 0), shift.id in mine)
            minutes = travel_for(c, viewer.origin(origin), viewer.transport, estimator)
        booking = mine.get(shift.id)
        check_from, check_to = check_in_window(shift.starts_at)
        deals.append(
            Deal(
                id=str(shift.id),
                title=shift.title,
                org=Org(id=str(org.id), name=org.name, verified=org.status is OrgStatus.VERIFIED),
                category=shift.category.value,
                starts_at=shift.starts_at,
                ends_at=shift.ends_at,
                hours=float(shift_hours(shift.starts_at, shift.ends_at)),
                address=shift.address,
                address_note=shift.address_note or None,
                description=shift.description,
                travel_min=minutes,
                capacity=shift.capacity,
                quorum=shift.quorum,
                taken=taken.get(shift.id, 0),
                going_initials=initials.get(shift.id, []),
                check_in_from=check_from,
                check_in_to=check_to,
                cancel_until=cancel_until(shift.starts_at),
                instructions_at=instructions_at(
                    shift.starts_at, booking.created_at if booking is not None else now
                ),
                my_booking=booking_out(booking) if booking is not None else None,
                impact=shift.impact or None,
            )
        )
    return deals

async def shift_with_org(
    session: AsyncSession, shift_id: uuid.UUID | str, *, for_update: bool = False
) -> tuple[Shift, OrgModel] | None:
    try:
        sid = shift_id if isinstance(shift_id, uuid.UUID) else uuid.UUID(shift_id)
    except ValueError:
        return None
    q = select(Shift, OrgModel).join(OrgModel, OrgModel.id == Shift.org_id).where(Shift.id == sid)
    if for_update:
        q = q.with_for_update(of=Shift)
    row = (await session.execute(q)).first()
    return None if row is None else (row[0], row[1])

def parse_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None

async def open_candidates(
    session: AsyncSession, viewer: Viewer, now: datetime, until: datetime
) -> tuple[list[tuple[Shift, OrgModel]], list[Candidate]]:
    rows = [
        (s, o)
        for s, o in (
            await session.execute(
                select(Shift, OrgModel)
                .join(OrgModel, OrgModel.id == Shift.org_id)
                .where(
                    Shift.status == ShiftStatus.OPEN,
                    OrgModel.status == OrgStatus.VERIFIED,
                    Shift.starts_at > now,
                    Shift.starts_at <= until,
                )
                .order_by(Shift.starts_at, Shift.id)
            )
        )
    ]
    ids = [s.id for s, _ in rows]
    taken = await taken_counts(session, ids)
    mine = await my_bookings(session, viewer.user, ids)
    candidates = [candidate(s, o, taken.get(s.id, 0), s.id in mine) for s, o in rows]
    return rows, candidates
