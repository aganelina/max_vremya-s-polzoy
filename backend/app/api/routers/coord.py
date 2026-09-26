import uuid
from collections.abc import Sequence
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query, Response
from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import Forbidden, NotFound
from app.api.routers.files import FileLink, make_file_link
from app.api.schemas import coord as s
from app.api.throttle import sensitive_limiter
from app.auth.deps import Coordinator, DbSession, Now
from app.config import get_settings
from app.db.enums import (
    BookingStatus,
    Category,
    LedgerSource,
    MessageAudience,
    MicroAnswerStatus,
    NotifyMode,
    OrgStatus,
    ShiftPlace,
    ShiftStatus,
)
from app.db.models import (
    Booking,
    DistrictAdjacency,
    FreeWindow,
    HourLedger,
    Job,
    Message,
    MicroAnswer,
    MicroTask,
    Org,
    OrgMember,
    Shift,
    University,
    UrgentCall,
    UrgentRecipient,
    User,
)
from app.domain import checkin_code
from app.domain.coord import (
    CAME_STATUSES,
    GOING_STATUSES,
    MESSAGE_MAX,
    MICRO_MINUTES_RANGE,
    MICRO_TEXT_MAX,
    MICRO_TITLE_MAX,
    URGENT_DURATION_MIN,
    URGENT_PEOPLE_RANGE,
    CoordError,
    CsvRow,
    UrgentCandidate,
    attendance_csv,
    can_undo_review,
    local_start,
    micro_hours,
    participant_status,
    pick_recipients,
    recipient_limit,
    validate_new_shift,
)
from app.domain.hours import credit_booking, remove_credited, uncredit_booking
from app.domain.metrics import compute_metrics
from app.domain.org_access import (
    active_invite,
    create_invite,
    invite_link,
    set_revoked,
    transfer_ownership,
)
from app.domain.travel import Point, haversine_km
from app.worker.queue import enqueue

router = APIRouter(prefix="/coord", tags=["coord"])

NEAR_CAMPUS_KM = 3.0

def _uuid(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise NotFound() from None

def org_view(org: Org) -> s.Org:
    return s.Org(id=str(org.id), name=org.name, verified=org.status is OrgStatus.VERIFIED)

async def _booked_counts(
    session: AsyncSession, shift_ids: Sequence[uuid.UUID], statuses: Sequence[BookingStatus]
) -> dict[uuid.UUID, int]:
    if not shift_ids:
        return {}
    rows = await session.execute(
        select(Booking.shift_id, func.count())
        .where(Booking.shift_id.in_(shift_ids), Booking.status.in_(statuses))
        .group_by(Booking.shift_id)
    )
    return {shift_id: n for shift_id, n in rows}

_NOT_CANCELLED = [st for st in BookingStatus if st is not BookingStatus.CANCELLED]

def shift_view(shift: Shift, org: Org, booked: int) -> s.Shift:
    return s.Shift(
        id=str(shift.id),
        title=shift.title,
        org=org_view(org),
        category=shift.category.value,
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
        address=shift.address,
        capacity=shift.capacity,
        booked=booked,
        quorum=shift.quorum,
        instructions=shift.instructions,
        place=shift.place.value,
        status=shift.status.value,
    )

async def _shift_views(session: AsyncSession, shifts: Sequence[Shift], org: Org) -> list[s.Shift]:
    counts = await _booked_counts(session, [x.id for x in shifts], _NOT_CANCELLED)
    return [shift_view(x, org, counts.get(x.id, 0)) for x in shifts]

async def own_shift(
    session: AsyncSession, ctx: Coordinator, shift_id: str, *, lock: bool = False
) -> Shift:
    stmt = select(Shift).where(Shift.id == _uuid(shift_id), Shift.org_id == ctx.org.id)
    if lock:
        stmt = stmt.with_for_update()
    shift = await session.scalar(stmt)
    if shift is None:
        raise NotFound("shift_not_found")
    return shift

@router.get("/home", response_model=s.CoordinatorHome)
async def coord_home(ctx: Coordinator, session: DbSession, now: Now) -> s.CoordinatorHome:
    shifts = list(
        await session.scalars(
            select(Shift)
            .where(
                Shift.org_id == ctx.org.id,
                Shift.status == ShiftStatus.OPEN,
                Shift.ends_at > now,
            )
            .order_by(Shift.starts_at, Shift.id)
        )
    )
    views = await _shift_views(session, shifts, ctx.org)
    if not shifts:
        return s.CoordinatorHome(next=None, shifts=[])
    going = await _booked_counts(session, [shifts[0].id], GOING_STATUSES)
    return s.CoordinatorHome(
        next=s.NextShift(shift=views[0], going=going.get(shifts[0].id, 0)),
        shifts=views[1:],
    )

async def _attendance(session: AsyncSession, shift: Shift, org: Org) -> s.ShiftAttendance:
    rows = await session.execute(
        select(Booking, User.first_name)
        .join(User, User.id == Booking.user_id)
        .where(Booking.shift_id == shift.id, Booking.status != BookingStatus.CANCELLED)
        .order_by(Booking.created_at, Booking.id)
    )
    participants = [
        s.Participant(
            id=str(b.user_id),
            first_name=name,
            status=participant_status(b.status, b.checked_in_at, shift.starts_at),
            checked_in_at=b.checked_in_at,
        )
        for b, name in rows
    ]
    return s.ShiftAttendance(
        shift=shift_view(shift, org, len(participants)), participants=participants
    )

@router.get("/shifts/{shift_id}/attendance", response_model=s.ShiftAttendance)
async def attendance(shift_id: str, ctx: Coordinator, session: DbSession) -> s.ShiftAttendance:
    shift = await own_shift(session, ctx, shift_id)
    return await _attendance(session, shift, ctx.org)

async def _participant_booking(session: AsyncSession, shift: Shift, pid: str) -> Booking:
    booking = await session.scalar(
        select(Booking)
        .where(
            Booking.shift_id == shift.id,
            Booking.user_id == _uuid(pid),
            Booking.status != BookingStatus.CANCELLED,
        )
        .with_for_update()
    )
    if booking is None:
        raise NotFound("participant_not_found")
    return booking

@router.put("/shifts/{shift_id}/participants/{pid}/manual", response_model=s.ShiftAttendance)
async def mark_manual(
    shift_id: str, pid: str, ctx: Coordinator, session: DbSession, now: Now
) -> s.ShiftAttendance:
    if _uuid(pid) == ctx.user.id:
        raise CoordError(409, "self_mark")
    shift = await own_shift(session, ctx, shift_id, lock=True)
    if shift.status is ShiftStatus.CANCELLED:
        raise CoordError(409, "shift_cancelled")
    booking = await _participant_booking(session, shift, pid)
    if booking.status in (BookingStatus.GOING, BookingStatus.NO_SHOW):
        booking.checked_in_at = now
        if shift.status is ShiftStatus.FINISHED:
            await credit_booking(session, booking, shift)
        else:
            booking.status = BookingStatus.MANUAL
    await session.commit()
    return await _attendance(session, shift, ctx.org)

@router.delete("/shifts/{shift_id}/participants/{pid}/manual", response_model=s.ShiftAttendance)
async def unmark_manual(
    shift_id: str, pid: str, ctx: Coordinator, session: DbSession, now: Now
) -> s.ShiftAttendance:
    shift = await own_shift(session, ctx, shift_id, lock=True)
    booking = await _participant_booking(session, shift, pid)
    if booking.status in (BookingStatus.MANUAL, BookingStatus.CHECKED_IN):
        booking.status = BookingStatus.GOING
        booking.checked_in_at = None
    elif booking.status is BookingStatus.DONE and shift.status is ShiftStatus.FINISHED:
        await uncredit_booking(session, booking, now)
    await session.commit()
    return await _attendance(session, shift, ctx.org)

@router.get("/shifts/{shift_id}/code", response_model=s.CheckInCode)
async def checkin_code_view(
    shift_id: str, ctx: Coordinator, session: DbSession, now: Now
) -> s.CheckInCode:
    shift = await own_shift(session, ctx, shift_id)
    if shift.status is ShiftStatus.CANCELLED:
        raise CoordError(409, "shift_cancelled")
    code = checkin_code.current_code(shift.checkin_secret, now)
    return s.CheckInCode(code=code.code, qr_payload=code.qr_payload, expires_at=code.expires_at)

@router.post("/shifts/{shift_id}/cancel", status_code=204)
async def cancel_shift(shift_id: str, ctx: Coordinator, session: DbSession, now: Now) -> Response:
    shift = await own_shift(session, ctx, shift_id, lock=True)
    if shift.status is ShiftStatus.CANCELLED:
        return Response(status_code=204)
    if shift.status is ShiftStatus.FINISHED or shift.starts_at <= now:
        raise CoordError(409, "shift_started")
    shift.status = ShiftStatus.CANCELLED
    bookings = list(
        await session.scalars(
            select(Booking).where(Booking.shift_id == shift.id, Booking.status.in_(GOING_STATUSES))
        )
    )
    for booking in bookings:
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
    await enqueue(
        session,
        "notify.shift_cancelled",
        {"shift_id": str(shift.id), "user_ids": [str(b.user_id) for b in bookings]},
    )
    await session.commit()
    return Response(status_code=204)

@router.post("/shifts", response_model=s.Shift)
async def create_shift(body: s.NewShift, ctx: Coordinator, session: DbSession, now: Now) -> s.Shift:
    tz = get_settings().tz
    starts_at = local_start(body.date, body.time, tz)
    title = validate_new_shift(body.title, starts_at, body.duration_min, body.capacity, now)
    org = ctx.org
    online = body.place == "online"
    shift = Shift(
        org_id=org.id,
        title=title,
        category=Category(body.category),
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=body.duration_min),
        capacity=body.capacity,
        quorum=body.quorum,
        place=ShiftPlace(body.place),
        address="Онлайн" if online else org.address,
        lat=None if online else org.lat,
        lon=None if online else org.lon,
        district_id=None if online else org.district_id,
        instructions=body.instructions.strip(),
        status=ShiftStatus.OPEN,
        checkin_secret=checkin_code.new_secret(),
        created_by=ctx.user.id,
    )
    session.add(shift)
    await session.flush()
    await enqueue(session, "shift.offer", {"shift_id": str(shift.id)})
    await session.commit()
    return shift_view(shift, org, 0)

async def _urgent_candidates(
    session: AsyncSession, ctx: Coordinator, shift: Shift
) -> list[UrgentCandidate]:
    org = ctx.org
    members = select(OrgMember.user_id).where(OrgMember.org_id == org.id)
    busy = (
        select(Booking.user_id)
        .join(Shift, Shift.id == Booking.shift_id)
        .where(
            Booking.status.in_(GOING_STATUSES),
            Shift.starts_at < shift.ends_at,
            Shift.ends_at > shift.starts_at,
        )
    )
    window = (
        select(FreeWindow.user_id)
        .where(FreeWindow.starts_at <= shift.starts_at, FreeWindow.ends_at > shift.starts_at)
        .distinct()
    )
    rows = await session.execute(
        select(User.id, User.district_id, University.lat, University.lon)
        .outerjoin(University, University.id == User.university_id)
        .where(
            User.consent_at.is_not(None),
            User.onboarded_at.is_not(None),
            User.notify == NotifyMode.ALL,
            User.id.not_in(members),
            User.id.not_in(busy),
        )
        .order_by(User.created_at, User.id)
        .limit(5000)
    )
    with_window = set(await session.scalars(window))
    near_districts: set[str] = set()
    if org.district_id:
        near_districts = {org.district_id} | set(
            await session.scalars(
                select(DistrictAdjacency.neighbor_id).where(
                    DistrictAdjacency.district_id == org.district_id
                )
            )
        )
    result = []
    for user_id, district_id, u_lat, u_lon in rows:
        near_campus = (
            org.lat is not None
            and org.lon is not None
            and u_lat is not None
            and u_lon is not None
            and haversine_km(Point(u_lat, u_lon), Point(org.lat, org.lon)) <= NEAR_CAMPUS_KM
        )
        result.append(
            UrgentCandidate(
                user_id=user_id,
                has_window=user_id in with_window,
                near_district=district_id in near_districts,
                near_campus=near_campus,
            )
        )
    return result

async def _urgent_status(session: AsyncSession, call: UrgentCall) -> s.UrgentCallStatus:
    rows = await session.execute(
        select(User.first_name, UrgentRecipient.responded_at)
        .join(User, User.id == UrgentRecipient.user_id)
        .where(UrgentRecipient.call_id == call.id, UrgentRecipient.responded_at.is_not(None))
        .order_by(UrgentRecipient.responded_at)
    )
    return s.UrgentCallStatus(
        id=str(call.id),
        shift_id=str(call.shift_id),
        what=call.what,
        people=call.people,
        reached=call.reached,
        responses=[s.UrgentResponse(name=name, at=at) for name, at in rows if at is not None],
    )

@router.post("/urgent", response_model=s.UrgentCallStatus)
async def urgent_call(
    body: s.UrgentCallIn, ctx: Coordinator, session: DbSession, now: Now
) -> s.UrgentCallStatus:
    sensitive_limiter.hit(f"urgent:{ctx.user.id}")
    if not URGENT_PEOPLE_RANGE[0] <= body.people <= URGENT_PEOPLE_RANGE[1]:
        raise CoordError(422, "invalid_people")
    org = ctx.org
    starts_at = now + timedelta(minutes=body.start_in_min)
    shift = Shift(
        org_id=org.id,
        title=body.what.strip()[:80],
        description=body.what.strip(),
        category=Category.PEOPLE,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=URGENT_DURATION_MIN),
        capacity=body.people,
        place=ShiftPlace.ORG,
        address=body.where.strip(),
        lat=org.lat,
        lon=org.lon,
        district_id=org.district_id,
        status=ShiftStatus.OPEN,
        checkin_secret=checkin_code.new_secret(),
        created_by=ctx.user.id,
    )
    session.add(shift)
    await session.flush()
    chosen = pick_recipients(
        await _urgent_candidates(session, ctx, shift), recipient_limit(body.people)
    )
    call = UrgentCall(
        org_id=org.id,
        shift_id=shift.id,
        what=body.what.strip(),
        where_text=body.where.strip(),
        start_in_min=body.start_in_min,
        people=body.people,
        reached=len(chosen),
        created_by=ctx.user.id,
    )
    session.add(call)
    await session.flush()
    for c in chosen:
        session.add(UrgentRecipient(call_id=call.id, user_id=c.user_id))
    await session.flush()
    await enqueue(session, "notify.urgent_call", {"call_id": str(call.id)})
    await session.commit()
    return await _urgent_status(session, call)

@router.get("/urgent/{call_id}", response_model=s.UrgentCallStatus)
async def urgent_status(call_id: str, ctx: Coordinator, session: DbSession) -> s.UrgentCallStatus:
    call = await session.scalar(
        select(UrgentCall).where(UrgentCall.id == _uuid(call_id), UrgentCall.org_id == ctx.org.id)
    )
    if call is None:
        raise NotFound("urgent_not_found")
    return await _urgent_status(session, call)

def _local_day_start(now: datetime) -> datetime:
    tz = get_settings().tz
    return local_start(now.astimezone(tz).date(), datetime.min.time(), tz)

@router.get("/reviews", response_model=s.ReviewQueue)
async def review_queue(ctx: Coordinator, session: DbSession, now: Now) -> s.ReviewQueue:
    rows = await session.execute(
        select(MicroAnswer, MicroTask, User.first_name)
        .join(MicroTask, MicroTask.id == MicroAnswer.task_id)
        .join(User, User.id == MicroAnswer.user_id)
        .where(MicroTask.org_id == ctx.org.id, MicroAnswer.status == MicroAnswerStatus.SENT)
        .order_by(MicroAnswer.created_at, MicroAnswer.id)
    )
    items = [
        s.ReviewItem(
            id=str(a.id), author_name=name, minutes=t.minutes, task=t.title, answer=a.answer
        )
        for a, t, name in rows
    ]
    today = await session.execute(
        select(MicroAnswer.status, func.count())
        .join(MicroTask, MicroTask.id == MicroAnswer.task_id)
        .where(
            MicroTask.org_id == ctx.org.id,
            MicroAnswer.reviewed_at >= _local_day_start(now),
            MicroAnswer.status.in_((MicroAnswerStatus.ACCEPTED, MicroAnswerStatus.RETURNED)),
        )
        .group_by(MicroAnswer.status)
    )
    counts = {st: n for st, n in today}
    return s.ReviewQueue(
        items=items,
        accepted_today=counts.get(MicroAnswerStatus.ACCEPTED, 0),
        returned_today=counts.get(MicroAnswerStatus.RETURNED, 0),
    )

async def _own_answer(
    session: AsyncSession, ctx: Coordinator, answer_id: str
) -> tuple[MicroAnswer, MicroTask]:
    row = (
        await session.execute(
            select(MicroAnswer, MicroTask)
            .join(MicroTask, MicroTask.id == MicroAnswer.task_id)
            .where(MicroAnswer.id == _uuid(answer_id), MicroTask.org_id == ctx.org.id)
            .with_for_update(of=MicroAnswer)
        )
    ).first()
    if row is None:
        raise NotFound("review_not_found")
    return row[0], row[1]

def _review_job_filter(answer_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
    return (
        Job.kind == "notify.micro_reviewed",
        Job.done_at.is_(None),
        Job.payload["answer_id"].astext == str(answer_id),
    )

@router.post("/reviews/{answer_id}", status_code=204)
async def review(
    answer_id: str, body: s.ReviewIn, ctx: Coordinator, session: DbSession, now: Now
) -> Response:
    answer, task = await _own_answer(session, ctx, answer_id)
    if answer.user_id == ctx.user.id:
        raise CoordError(409, "self_review")
    if answer.status is not MicroAnswerStatus.SENT:
        raise CoordError(409, "already_reviewed")
    note = (body.note or "").strip()
    if body.verdict == "return":
        if not note:
            raise CoordError(422, "note_required")
        answer.status = MicroAnswerStatus.RETURNED
        answer.review_note = note[:500]
    else:
        answer.status = MicroAnswerStatus.ACCEPTED
        answer.review_note = note[:500] or None
        session.add(
            HourLedger(
                user_id=answer.user_id,
                source=LedgerSource.MICRO,
                ref_id=answer.id,
                hours=micro_hours(task.minutes),
                org_id=task.org_id,
                accepted_at=now,
            )
        )
    answer.reviewed_by = ctx.user.id
    answer.reviewed_at = now
    await enqueue(
        session,
        "notify.micro_reviewed",
        {"answer_id": str(answer.id)},
        run_at=now + timedelta(minutes=10),
    )
    await session.commit()
    return Response(status_code=204)

@router.delete("/reviews/{answer_id}", status_code=204)
async def undo_review(answer_id: str, ctx: Coordinator, session: DbSession, now: Now) -> Response:
    answer, _ = await _own_answer(session, ctx, answer_id)
    if answer.status not in (MicroAnswerStatus.ACCEPTED, MicroAnswerStatus.RETURNED):
        raise CoordError(409, "not_reviewed")
    if not can_undo_review(answer.reviewed_at, now):
        raise CoordError(409, "undo_expired")
    await remove_credited(session, answer.user_id, LedgerSource.MICRO, answer.id, now)
    await session.execute(delete(Job).where(*_review_job_filter(answer.id)))
    answer.status = MicroAnswerStatus.SENT
    answer.review_note = None
    answer.reviewed_by = None
    answer.reviewed_at = None
    await session.commit()
    return Response(status_code=204)

async def _micro_views(session: AsyncSession, tasks: Sequence[MicroTask]) -> list[s.CoordMicroTask]:
    counts: dict[tuple[uuid.UUID, MicroAnswerStatus], int] = {}
    if tasks:
        rows = await session.execute(
            select(MicroAnswer.task_id, MicroAnswer.status, func.count())
            .where(MicroAnswer.task_id.in_([t.id for t in tasks]))
            .group_by(MicroAnswer.task_id, MicroAnswer.status)
        )
        counts = {(task_id, st): n for task_id, st, n in rows}
    return [
        s.CoordMicroTask(
            id=str(t.id),
            title=t.title,
            text=t.text,
            minutes=t.minutes,
            answers_needed=t.answers_needed,
            deadline=t.deadline_at,
            active=t.active,
            pending=counts.get((t.id, MicroAnswerStatus.SENT), 0),
            accepted=counts.get((t.id, MicroAnswerStatus.ACCEPTED), 0),
            created_at=t.created_at,
        )
        for t in tasks
    ]

@router.post("/micro-tasks", response_model=s.CoordMicroTask)
async def create_micro_task(
    body: s.NewMicroTask, ctx: Coordinator, session: DbSession, now: Now
) -> s.CoordMicroTask:
    title, text = body.title.strip(), body.text.strip()
    if not 1 <= len(title) <= MICRO_TITLE_MAX:
        raise CoordError(422, "invalid_title")
    if not 1 <= len(text) <= MICRO_TEXT_MAX:
        raise CoordError(422, "invalid_text")
    if not MICRO_MINUTES_RANGE[0] <= body.minutes <= MICRO_MINUTES_RANGE[1]:
        raise CoordError(422, "invalid_minutes")
    if body.deadline is not None and body.deadline <= now:
        raise CoordError(422, "deadline_in_past")
    task = MicroTask(
        org_id=ctx.org.id,
        title=title,
        text=text,
        minutes=body.minutes,
        answers_needed=body.answers_needed,
        deadline_at=body.deadline,
        active=True,
        created_by=ctx.user.id,
        created_at=now,
    )
    session.add(task)
    await session.commit()
    return (await _micro_views(session, [task]))[0]

@router.get("/micro-tasks", response_model=list[s.CoordMicroTask])
async def list_micro_tasks(ctx: Coordinator, session: DbSession) -> list[s.CoordMicroTask]:
    tasks = list(
        await session.scalars(
            select(MicroTask)
            .where(MicroTask.org_id == ctx.org.id)
            .order_by(MicroTask.active.desc(), MicroTask.created_at.desc(), MicroTask.id)
        )
    )
    return await _micro_views(session, tasks)

@router.patch("/micro-tasks/{task_id}", response_model=s.CoordMicroTask)
async def patch_micro_task(
    task_id: str, body: s.MicroTaskPatch, ctx: Coordinator, session: DbSession
) -> s.CoordMicroTask:
    task = await session.scalar(
        select(MicroTask).where(MicroTask.id == _uuid(task_id), MicroTask.org_id == ctx.org.id)
    )
    if task is None:
        raise NotFound("micro_task_not_found")
    task.active = body.active
    await session.commit()
    return (await _micro_views(session, [task]))[0]

@router.get("/metrics", response_model=s.Metrics)
async def metrics(ctx: Coordinator, session: DbSession, now: Now) -> s.Metrics:
    view = await compute_metrics(session, now, own_org_id=ctx.org.id)
    return s.Metrics.model_validate(view)

async def _access(session: AsyncSession, ctx: Coordinator, now: Now) -> s.OrgAccess:
    tz = get_settings().tz
    local = now.astimezone(tz)
    month_from = local_start(local.date().replace(day=1), datetime.min.time(), tz)
    next_month = (month_from + timedelta(days=32)).replace(day=1)
    shifts_this_month = await session.scalar(
        select(func.count())
        .select_from(Shift)
        .where(
            Shift.org_id == ctx.org.id,
            Shift.status != ShiftStatus.CANCELLED,
            Shift.starts_at >= month_from,
            Shift.starts_at < next_month,
        )
    )
    members = await session.execute(
        select(OrgMember, User.first_name)
        .join(User, User.id == OrgMember.user_id)
        .where(OrgMember.org_id == ctx.org.id)
        .order_by(OrgMember.created_at, User.first_name)
    )
    invite = await active_invite(session, ctx.org.id, now) if ctx.is_owner else None
    return s.OrgAccess(
        org_name=ctx.org.name,
        shifts_this_month=int(shifts_this_month or 0),
        coordinators=[
            s.Coordinator(
                id=str(m.user_id),
                name=name,
                owner=m.role.value == "owner",
                me=m.user_id == ctx.user.id,
                revoked=m.revoked_at is not None,
            )
            for m, name in members
        ],
        invite=s.Invite(link=invite_link(invite.token), expires_at=invite.expires_at)
        if invite
        else None,
    )

def _require_owner(ctx: Coordinator) -> None:
    if not ctx.is_owner:
        raise Forbidden("not_owner")

@router.get("/access", response_model=s.OrgAccess)
async def access(ctx: Coordinator, session: DbSession, now: Now) -> s.OrgAccess:
    return await _access(session, ctx, now)

@router.post("/access/invites", response_model=s.OrgAccess)
async def invite_coordinator(ctx: Coordinator, session: DbSession, now: Now) -> s.OrgAccess:
    _require_owner(ctx)
    await create_invite(session, ctx.org.id, ctx.user.id, now)
    await session.commit()
    return await _access(session, ctx, now)

@router.post("/access/{member_id}/owner", response_model=s.OrgAccess)
async def transfer_owner(
    member_id: str, ctx: Coordinator, session: DbSession, now: Now
) -> s.OrgAccess:
    _require_owner(ctx)
    await transfer_ownership(session, ctx.org.id, ctx.user.id, _uuid(member_id))
    await session.commit()
    return await _access(session, ctx, now)

@router.patch("/access/{member_id}", response_model=s.OrgAccess)
async def set_coordinator_revoked(
    member_id: str, body: s.RevokeIn, ctx: Coordinator, session: DbSession, now: Now
) -> s.OrgAccess:
    _require_owner(ctx)
    await set_revoked(session, ctx.org.id, ctx.user.id, _uuid(member_id), body.revoked, now)
    await session.commit()
    return await _access(session, ctx, now)

def _parse_day(raw: str) -> date:
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        raise CoordError(422, "invalid_period") from None

def attendance_period(from_: str, to: str) -> tuple[date, date]:
    day_from, day_to = _parse_day(from_), _parse_day(to)
    if day_to < day_from:
        raise CoordError(422, "invalid_period")
    return day_from, day_to

def attendance_file_name(day_from: date, day_to: date) -> str:
    return f"attendance_{day_from.isoformat()}_{day_to.isoformat()}.csv"

async def attendance_csv_bytes(
    session: AsyncSession, org_id: uuid.UUID, day_from: date, day_to: date
) -> bytes:
    tz = get_settings().tz
    since = local_start(day_from, datetime.min.time(), tz)
    until = local_start(day_to + timedelta(days=1), datetime.min.time(), tz)
    rows = await session.execute(
        select(Shift, Booking, User.first_name, HourLedger.hours)
        .join(Booking, Booking.shift_id == Shift.id)
        .join(User, User.id == Booking.user_id)
        .outerjoin(
            HourLedger,
            (HourLedger.source == LedgerSource.SHIFT)
            & (HourLedger.ref_id == Booking.id)
            & (HourLedger.user_id == Booking.user_id),
        )
        .where(
            Shift.org_id == org_id,
            Shift.starts_at >= since,
            Shift.starts_at < until,
            Booking.status != BookingStatus.CANCELLED,
        )
        .order_by(Shift.starts_at, Shift.title, Booking.created_at)
    )
    body = attendance_csv(
        [
            CsvRow(
                starts_at=shift.starts_at,
                shift=shift.title,
                name=name,
                status=participant_status(b.status, b.checked_in_at, shift.starts_at),
                checked_in_at=b.checked_in_at,
                hours=hours,
            )
            for shift, b, name, hours in rows
        ],
        tz,
    )
    return body.encode("utf-8")

def csv_response(content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/attendance.csv")
async def attendance_export(
    ctx: Coordinator,
    session: DbSession,
    from_: str = Query(alias="from"),
    to: str = Query(),
) -> Response:
    day_from, day_to = attendance_period(from_, to)
    content = await attendance_csv_bytes(session, ctx.org.id, day_from, day_to)
    return csv_response(content, attendance_file_name(day_from, day_to))

@router.post("/attendance/link", response_model=FileLink)
async def attendance_link(
    ctx: Coordinator,
    now: Now,
    from_: str = Query(alias="from"),
    to: str = Query(),
) -> FileLink:
    """Короткоживущая ссылка на тот же CSV — для WebApp.downloadFile в MAX."""
    day_from, day_to = attendance_period(from_, to)
    return make_file_link(
        {
            "k": "attendance",
            "u": str(ctx.user.id),
            "o": str(ctx.org.id),
            "f": day_from.isoformat(),
            "t": day_to.isoformat(),
        },
        attendance_file_name(day_from, day_to),
        now,
    )

_AUDIENCE_STATUSES: dict[MessageAudience, tuple[BookingStatus, ...]] = {
    MessageAudience.ALL: tuple(_NOT_CANCELLED),
    MessageAudience.WAITING: (BookingStatus.GOING,),
    MessageAudience.CAME: CAME_STATUSES,
}

async def _audience_names(
    session: AsyncSession, shift: Shift, audience: MessageAudience
) -> list[str]:
    names = await session.scalars(
        select(User.first_name)
        .join(Booking, Booking.user_id == User.id)
        .where(Booking.shift_id == shift.id, Booking.status.in_(_AUDIENCE_STATUSES[audience]))
        .order_by(Booking.created_at, Booking.id)
    )
    return list(names)

@router.get("/shifts/{shift_id}/audiences", response_model=list[s.Audience])
async def audiences(shift_id: str, ctx: Coordinator, session: DbSession) -> list[s.Audience]:
    shift = await own_shift(session, ctx, shift_id)
    return [
        s.Audience(key=a.value, names=await _audience_names(session, shift, a))
        for a in MessageAudience
    ]

@router.post("/shifts/{shift_id}/messages", response_model=s.MessageSent)
async def message_participants(
    shift_id: str, body: s.MessageIn, ctx: Coordinator, session: DbSession, now: Now
) -> s.MessageSent:
    sensitive_limiter.hit(f"messages:{ctx.user.id}")
    shift = await own_shift(session, ctx, shift_id)
    text = body.text.strip()
    if not 1 <= len(text) <= MESSAGE_MAX:
        raise CoordError(422, "invalid_text")
    audience = MessageAudience(body.audience)
    sent = len(await _audience_names(session, shift, audience))
    message = Message(
        shift_id=shift.id,
        audience=audience,
        text=text,
        sent_count=sent,
        created_by=ctx.user.id,
        created_at=now,
    )
    session.add(message)
    await session.flush()
    if sent:
        await enqueue(session, "notify.coord_message", {"message_id": str(message.id)})
    await session.commit()
    return s.MessageSent(sent=sent)
