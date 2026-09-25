import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import Conflict, Forbidden, NotFound
from app.config import get_settings
from app.db.enums import BookingStatus, MentorRequestStatus, ShiftStatus
from app.db.models import Booking, MentorRequest, MentorSettings, Org, Shift, User
from app.worker.queue import enqueue

MENTORS_PER_REQUEST = 5
SEAT_STATUSES = (
    BookingStatus.GOING,
    BookingStatus.CHECKED_IN,
    BookingStatus.DONE,
    BookingStatus.MANUAL,
    BookingStatus.NO_SHOW,
)
BUSY_STATUSES = (BookingStatus.GOING, BookingStatus.CHECKED_IN, BookingStatus.MANUAL)

def is_eligible(deals_done: int, required: int) -> bool:
    return deals_done >= required

def interests_overlap(mentor: Sequence[str], wanted: Sequence[str]) -> bool:
    return bool(set(mentor) & set(wanted))

async def done_deals(session: AsyncSession, user_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.user_id == user_id, Booking.status == BookingStatus.DONE)
    )
    return int(count or 0)

async def is_accepting(session: AsyncSession, user_id: uuid.UUID) -> bool:
    settings = await session.get(MentorSettings, user_id)
    return bool(settings and settings.accepting)

async def book_on_shift(
    session: AsyncSession, user: User, shift_id: uuid.UUID, now: datetime
) -> Booking:
    from app.domain.booking import create_booking

    booking, _ = await create_booking(session, user, shift_id, now)
    return booking

async def create_mentor_requests_for_booking(
    session: AsyncSession, booking: Booking
) -> list[MentorRequest]:
    if booking.status is not BookingStatus.GOING:
        return []
    newbie = await session.get(User, booking.user_id)
    shift = await session.get(Shift, booking.shift_id)
    if newbie is None or shift is None:
        return []
    earlier = await session.scalar(
        select(func.count())
        .select_from(Booking)
        .where(
            Booking.user_id == newbie.id,
            Booking.id != booking.id,
            Booking.status != BookingStatus.CANCELLED,
        )
    )
    if earlier or await done_deals(session, newbie.id):
        return []
    already = await session.scalar(
        select(func.count())
        .select_from(MentorRequest)
        .where(MentorRequest.newbie_id == newbie.id, MentorRequest.shift_id == shift.id)
    )
    if already:
        return []

    wanted = sorted({*newbie.interests, shift.category.value})
    done = (
        select(Booking.user_id, func.count().label("done"))
        .where(Booking.status == BookingStatus.DONE)
        .group_by(Booking.user_id)
        .subquery()
    )
    on_shift = select(Booking.user_id).where(
        Booking.shift_id == shift.id, Booking.status != BookingStatus.CANCELLED
    )
    mentors = (
        await session.scalars(
            select(User.id)
            .join(MentorSettings, MentorSettings.user_id == User.id)
            .join(done, done.c.user_id == User.id)
            .where(
                MentorSettings.accepting.is_(True),
                done.c.done >= get_settings().mentor_min_deals,
                User.id != newbie.id,
                User.id.not_in(on_shift),
                User.interests.overlap(wanted),
            )
            .order_by(
                (User.district_id == newbie.district_id).desc(),
                (User.university_id == newbie.university_id).desc(),
                done.c.done.desc(),
                User.id,
            )
            .limit(MENTORS_PER_REQUEST)
        )
    ).all()
    created: list[MentorRequest] = []
    for mentor_id in mentors:
        request = MentorRequest(
            newbie_id=newbie.id,
            shift_id=shift.id,
            mentor_id=mentor_id,
            status=MentorRequestStatus.OPEN,
        )
        session.add(request)
        created.append(request)
    await session.flush()
    for request in created:
        await enqueue(session, "notify.mentor_request", {"request_id": str(request.id)})
    return created

@dataclass(frozen=True)
class RequestRow:
    request: MentorRequest
    shift: Shift
    org: Org
    newbie_name: str

@dataclass(frozen=True)
class MentorshipView:
    eligible: bool
    deals_done: int
    deals_required: int
    accepting: bool
    requests: list[RequestRow]
    pairs: list[RequestRow]

async def _rows(
    session: AsyncSession,
    mentor_id: uuid.UUID,
    status: MentorRequestStatus,
    *conditions: ColumnElement[bool],
) -> list[RequestRow]:
    rows = (
        await session.execute(
            select(MentorRequest, Shift, Org, User.first_name)
            .join(Shift, Shift.id == MentorRequest.shift_id)
            .join(Org, Org.id == Shift.org_id)
            .join(User, User.id == MentorRequest.newbie_id)
            .where(MentorRequest.mentor_id == mentor_id, MentorRequest.status == status)
            .where(*conditions)
            .order_by(Shift.starts_at, MentorRequest.id)
        )
    ).all()
    return [RequestRow(r, s, o, name) for r, s, o, name in rows]

async def mentorship_view(session: AsyncSession, user: User, now: datetime) -> MentorshipView:
    required = get_settings().mentor_min_deals
    deals = await done_deals(session, user.id)
    eligible = is_eligible(deals, required)
    accepting = eligible and await is_accepting(session, user.id)
    requests = (
        await _rows(
            session,
            user.id,
            MentorRequestStatus.OPEN,
            Shift.status == ShiftStatus.OPEN,
            Shift.starts_at > now,
        )
        if accepting
        else []
    )
    pairs = await _rows(session, user.id, MentorRequestStatus.ACCEPTED)
    return MentorshipView(
        eligible=eligible,
        deals_done=deals,
        deals_required=required,
        accepting=accepting,
        requests=requests,
        pairs=pairs,
    )

async def set_accepting(session: AsyncSession, user: User, accepting: bool) -> None:
    if accepting and not is_eligible(
        await done_deals(session, user.id), get_settings().mentor_min_deals
    ):
        raise Forbidden("not_eligible")
    await session.execute(
        pg_insert(MentorSettings)
        .values(user_id=user.id, accepting=accepting)
        .on_conflict_do_update(
            index_elements=[MentorSettings.user_id], set_={"accepting": accepting}
        )
    )

async def _open_request(session: AsyncSession, user: User, request_id: uuid.UUID) -> MentorRequest:
    request = await session.scalar(
        select(MentorRequest)
        .where(MentorRequest.id == request_id, MentorRequest.mentor_id == user.id)
        .with_for_update()
    )
    if request is None:
        raise NotFound()
    if request.status is not MentorRequestStatus.OPEN:
        raise Conflict("request_closed")
    return request

async def accept_request(
    session: AsyncSession, user: User, request_id: uuid.UUID, now: datetime
) -> Booking:
    if not is_eligible(await done_deals(session, user.id), get_settings().mentor_min_deals):
        raise Forbidden("not_eligible")
    request = await _open_request(session, user, request_id)
    newbie_going = await session.scalar(
        select(Booking.id).where(
            Booking.shift_id == request.shift_id,
            Booking.user_id == request.newbie_id,
            Booking.status.in_(BUSY_STATUSES),
        )
    )
    if newbie_going is None:
        request.status = MentorRequestStatus.EXPIRED
        await session.commit()
        raise Conflict("request_closed")
    booking = await book_on_shift(session, user, request.shift_id, now)
    request.status = MentorRequestStatus.ACCEPTED
    await session.execute(
        update(MentorRequest)
        .where(
            MentorRequest.newbie_id == request.newbie_id,
            MentorRequest.shift_id == request.shift_id,
            MentorRequest.id != request.id,
            MentorRequest.status == MentorRequestStatus.OPEN,
        )
        .values(status=MentorRequestStatus.EXPIRED)
    )
    await session.flush()
    return booking

async def decline_request(session: AsyncSession, user: User, request_id: uuid.UUID) -> None:
    request = await _open_request(session, user, request_id)
    request.status = MentorRequestStatus.DECLINED
    await session.flush()
