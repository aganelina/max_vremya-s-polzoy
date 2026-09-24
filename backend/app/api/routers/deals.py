from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from sqlalchemy import and_, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deal_view import (
    booking_out,
    build_deals,
    load_viewer,
    parse_uuid,
    shift_with_org,
)
from app.api.errors import Conflict, NotFound
from app.api.schemas.deals import (
    BookIn,
    Booking,
    CheckInIn,
    CheckInResult,
    Deal,
    FriendInvite,
    HistoryItem,
    Link,
    MyDeals,
    PastBooking,
    SeatTransfer,
)
from app.api.throttle import SlidingWindow
from app.auth.deps import CurrentUser, DbSession, Now, OnboardedUser
from app.config import get_settings
from app.db.enums import BookingStatus, OrgStatus, ShiftStatus, TransferStatus
from app.db.models import Booking as BookingModel
from app.db.models import CompanyMember, Org, Shift, User
from app.db.models import FriendInvite as InviteModel
from app.db.models import SeatTransfer as TransferModel
from app.domain import checkin_code
from app.domain.booking import create_booking, lock_shift, lock_user_bookings
from app.domain.credits import credited_rows
from app.domain.deal_times import check_in_window, is_late, planned_instructions_at
from app.domain.hours import to_hours
from app.domain.ics import build_event
from app.domain.links import new_token, startapp_link
from app.domain.participant_settings import participant_settings

router = APIRouter(tags=["deals"])

checkin_limiter = SlidingWindow(participant_settings().checkin_rate_per_min)

MICRO_PLACE = "микро-дело в чате"

async def _deal(
    session: AsyncSession, user: User | None, shift_id: str, now: datetime, origin: str = "campus"
) -> Deal:
    row = await shift_with_org(session, shift_id)
    if row is None:
        raise NotFound("deal_not_found")
    viewer = await load_viewer(session, user)
    return (await build_deals(session, [row], viewer, now, origin=origin))[0]

async def _own_booking(
    session: AsyncSession, user: User, booking_id: str, *, for_update: bool = False
) -> BookingModel:
    bid = parse_uuid(booking_id)
    q = select(BookingModel).where(BookingModel.id == bid, BookingModel.user_id == user.id)
    if for_update:
        q = q.with_for_update()
    booking = await session.scalar(q) if bid is not None else None
    if booking is None:
        raise NotFound("booking_not_found")
    return booking

@router.get("/events", response_model=list[Deal])
async def events(
    user: OnboardedUser,
    session: DbSession,
    now: Now,
    day: Annotated[date, Query(alias="date")],
) -> list[Deal]:
    """Афиша на выбранный день, независимо от личного свободного окна."""
    start = datetime.combine(day, time.min, tzinfo=get_settings().tz)
    rows = await session.execute(
        select(Shift, Org)
        .join(Org, Org.id == Shift.org_id)
        .where(
            Shift.status == ShiftStatus.OPEN,
            Org.status == OrgStatus.VERIFIED,
            Shift.starts_at >= start,
            Shift.starts_at < start + timedelta(days=1),
            Shift.ends_at > now,
        )
        .order_by(Shift.starts_at, Shift.id)
    )
    return await build_deals(session, list(rows), await load_viewer(session, user), now)

@router.get("/deals/{deal_id}", response_model=Deal)
async def get_deal(
    deal_id: str,
    user: OnboardedUser,
    session: DbSession,
    now: Now,
    origin: Annotated[Literal["campus", "home"], Query(alias="from")] = "campus",
) -> Deal:
    return await _deal(session, user, deal_id, now, origin)

@router.post("/deals/{deal_id}/bookings", response_model=Booking)
async def book(
    deal_id: str, user: OnboardedUser, session: DbSession, now: Now, body: BookIn | None = None
) -> Booking:
    body = body or BookIn()
    sid = parse_uuid(deal_id)
    if sid is None:
        raise NotFound("deal_not_found")
    company_id = None
    if body.company_id:
        cid = parse_uuid(body.company_id)
        if cid is not None and await session.get(CompanyMember, (cid, user.id)) is not None:
            company_id = cid
    invite_id = None
    if body.invite_token:
        invite = await session.scalar(
            select(InviteModel).where(
                InviteModel.token == body.invite_token, InviteModel.shift_id == sid
            )
        )
        invite_id = invite.id if invite is not None else None
    booking, _ = await create_booking(
        session, user, sid, now, company_id=company_id, via_invite_id=invite_id
    )
    await session.commit()
    return booking_out(booking)

@router.delete("/bookings/{booking_id}", status_code=204)
async def cancel_booking(
    booking_id: str, user: OnboardedUser, session: DbSession, now: Now
) -> Response:
    booking = await _own_booking(session, user, booking_id, for_update=True)
    if booking.status is BookingStatus.CANCELLED:
        return Response(status_code=204)
    if booking.status is not BookingStatus.GOING:
        raise Conflict("already_checked_in")
    booking.status = BookingStatus.CANCELLED
    booking.cancelled_at = now
    transfers = await session.scalars(
        select(TransferModel).where(
            TransferModel.booking_id == booking.id, TransferModel.status == TransferStatus.OPEN
        )
    )
    for t in transfers:
        t.status = TransferStatus.EXPIRED
    await session.commit()
    return Response(status_code=204)

@router.post("/deals/{deal_id}/invite", response_model=Link)
async def invite_friend(deal_id: str, user: OnboardedUser, session: DbSession) -> Link:
    row = await shift_with_org(session, deal_id)
    if row is None:
        raise NotFound("deal_not_found")
    shift = row[0]
    invite = await session.scalar(
        select(InviteModel).where(
            InviteModel.shift_id == shift.id, InviteModel.inviter_id == user.id
        )
    )
    if invite is None:
        invite = InviteModel(token=new_token(), shift_id=shift.id, inviter_id=user.id)
        session.add(invite)
        await session.commit()
    return Link(link=startapp_link("fr", invite.token))

def _closed(shift: Shift, org: Org, now: datetime) -> bool:
    return (
        shift.status is not ShiftStatus.OPEN
        or org.status is not OrgStatus.VERIFIED
        or shift.starts_at <= now
    )

@router.get("/invites/{token}", response_model=FriendInvite)
async def get_invite(token: str, user: CurrentUser, session: DbSession, now: Now) -> FriendInvite:
    """fr_<token>: доступно до онбординга."""
    invite = await session.scalar(select(InviteModel).where(InviteModel.token == token))
    if invite is None:
        raise NotFound("invite_not_found")
    row = await shift_with_org(session, invite.shift_id)
    if row is None:
        raise NotFound("invite_not_found")
    shift, org = row
    inviter = await session.get(User, invite.inviter_id)
    deal = await _deal(session, user, str(shift.id), now)
    status: Literal["ok", "full", "expired"] = "ok"
    if _closed(shift, org, now):
        status = "expired"
    elif deal.my_booking is None and deal.taken >= deal.capacity:
        status = "full"
    return FriendInvite(
        status=status, inviter_name=inviter.first_name if inviter else None, deal=deal
    )

@router.get("/deals/{deal_id}/ics")
async def deal_ics(deal_id: str, session: DbSession, now: Now) -> Response:
    """Открывается браузером/календарём без initData — данные смены не личные."""
    row = await shift_with_org(session, deal_id)
    if (
        row is None
        or row[0].status is ShiftStatus.CANCELLED
        or row[1].status is not OrgStatus.VERIFIED
    ):
        raise NotFound("deal_not_found")
    shift, org = row
    location = shift.address + (f" ({shift.address_note})" if shift.address_note else "")
    settings = get_settings()
    shown = now >= planned_instructions_at(shift.starts_at, settings.tz, settings.instructions_hour)
    instructions = shift.instructions if shown else ""
    description = "\n\n".join(part for part in (org.name, shift.description, instructions) if part)
    body = build_event(
        uid=f"{shift.id}@vremya",
        starts_at=shift.starts_at,
        ends_at=shift.ends_at,
        summary=shift.title,
        location=location,
        description=description,
        stamp=now,
    )
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="deal.ics"'},
    )

@router.get("/me/deals", response_model=MyDeals)
async def my_deals(user: OnboardedUser, session: DbSession, now: Now) -> MyDeals:
    rows = await session.execute(
        select(Shift, Org)
        .join(Org, Org.id == Shift.org_id)
        .join(BookingModel, BookingModel.shift_id == Shift.id)
        .where(
            BookingModel.user_id == user.id,
            BookingModel.status.in_(
                (BookingStatus.GOING, BookingStatus.CHECKED_IN, BookingStatus.MANUAL)
            ),
            Shift.ends_at > now,
            Shift.status != ShiftStatus.CANCELLED,
        )
        .order_by(Shift.starts_at, Shift.id)
    )
    viewer = await load_viewer(session, user)
    upcoming = await build_deals(session, list(rows), viewer, now)
    history = [
        HistoryItem(
            id=str(r.id),
            title=r.title,
            date=r.date,
            place=MICRO_PLACE if r.micro else r.org_name,
            hours=to_hours(r.hours),
        )
        for r in await credited_rows(session, user.id)
    ]
    past_rows = (
        await session.execute(
            select(BookingModel, Shift)
            .join(Shift, Shift.id == BookingModel.shift_id)
            .where(
                BookingModel.user_id == user.id,
                not_(
                    and_(
                        BookingModel.status.in_(
                            (BookingStatus.GOING, BookingStatus.CHECKED_IN, BookingStatus.MANUAL)
                        ),
                        Shift.ends_at > now,
                        Shift.status != ShiftStatus.CANCELLED,
                    )
                ),
            )
            .order_by(Shift.starts_at.desc(), BookingModel.id)
        )
    ).all()
    past = [
        PastBooking(
            id=str(b.id),
            deal_id=str(s.id),
            title=s.title,
            starts_at=s.starts_at,
            status="cancelled" if s.status == ShiftStatus.CANCELLED else b.status.value,
            can_contact=b.status != BookingStatus.CANCELLED and s.status != ShiftStatus.CANCELLED,
        )
        for b, s in past_rows
    ]
    return MyDeals(upcoming=upcoming, history=history, past=past)

@router.post("/bookings/{booking_id}/check-in", response_model=CheckInResult)
async def check_in(
    booking_id: str, body: CheckInIn, user: OnboardedUser, session: DbSession, now: Now
) -> CheckInResult:
    checkin_limiter.hit(str(user.id))
    booking = await _own_booking(session, user, booking_id, for_update=True)
    shift = await session.get(Shift, booking.shift_id)
    assert shift is not None
    if booking.status in (BookingStatus.CHECKED_IN, BookingStatus.MANUAL, BookingStatus.DONE):
        at = booking.checked_in_at or now
        return CheckInResult(ok=True, checked_in_at=at, late=is_late(shift.starts_at, at))
    if booking.status is not BookingStatus.GOING or shift.status is ShiftStatus.CANCELLED:
        raise Conflict("booking_inactive")
    check_from, check_to = check_in_window(shift.starts_at)
    if now < check_from:
        return CheckInResult(ok=False, error="too_early")
    if now > check_to:
        return CheckInResult(ok=False, error="too_late")
    result = checkin_code.check(shift.checkin_secret, body.code, now)
    if result == checkin_code.CodeCheck.EXPIRED:
        return CheckInResult(ok=False, error="expired")
    if result != checkin_code.CodeCheck.OK:
        return CheckInResult(ok=False, error="wrong_code")
    booking.status = BookingStatus.CHECKED_IN
    booking.checked_in_at = now
    await session.commit()
    return CheckInResult(ok=True, checked_in_at=now, late=is_late(shift.starts_at, now))

@router.delete("/bookings/{booking_id}/check-in", status_code=204)
async def undo_check_in(booking_id: str, user: OnboardedUser, session: DbSession) -> Response:
    """«Отметка ошибочная»: только своя отметка по коду и до начисления часов."""
    booking = await _own_booking(session, user, booking_id, for_update=True)
    if booking.status is not BookingStatus.CHECKED_IN:
        raise Conflict("not_checked_in")
    booking.status = BookingStatus.GOING
    booking.checked_in_at = None
    await session.commit()
    return Response(status_code=204)

@router.post("/bookings/{booking_id}/transfer", response_model=Link)
async def create_transfer(
    booking_id: str, user: OnboardedUser, session: DbSession, now: Now
) -> Link:
    """Ссылка tr_<token>: место держится за передающим до начала смены."""
    booking = await _own_booking(session, user, booking_id)
    shift = await session.get(Shift, booking.shift_id)
    assert shift is not None
    if booking.status is not BookingStatus.GOING or shift.starts_at <= now:
        raise Conflict("booking_inactive")
    transfer = await session.scalar(
        select(TransferModel).where(
            TransferModel.booking_id == booking.id, TransferModel.status == TransferStatus.OPEN
        )
    )
    if transfer is None:
        transfer = TransferModel(
            booking_id=booking.id,
            token=new_token(),
            status=TransferStatus.OPEN,
            expires_at=shift.starts_at,
        )
        session.add(transfer)
        await session.commit()
    return Link(link=startapp_link("tr", transfer.token))

async def _transfer_state(
    session: AsyncSession, transfer: TransferModel, now: datetime
) -> tuple[Literal["ok", "taken", "expired"], BookingModel | None]:
    source = await session.get(BookingModel, transfer.booking_id)
    if transfer.status is TransferStatus.CLAIMED:
        return "taken", source
    if (
        transfer.status is TransferStatus.EXPIRED
        or transfer.expires_at <= now
        or source is None
        or source.status is not BookingStatus.GOING
    ):
        return "expired", source
    shift = await session.get(Shift, source.shift_id)
    if shift is None or shift.status is not ShiftStatus.OPEN:
        return "expired", source
    return "ok", source

@router.get("/transfers/{token}", response_model=SeatTransfer)
async def get_transfer(token: str, user: CurrentUser, session: DbSession, now: Now) -> SeatTransfer:
    transfer = await session.scalar(select(TransferModel).where(TransferModel.token == token))
    if transfer is None:
        return SeatTransfer(status="expired", from_name=None, deal=None)
    status, source = await _transfer_state(session, transfer, now)
    owner = await session.get(User, source.user_id) if source is not None else None
    deal = (
        await _deal(session, user, str(source.shift_id), now)
        if status == "ok" and source is not None
        else None
    )
    return SeatTransfer(
        status=status, from_name=owner.first_name if owner is not None else None, deal=deal
    )

@router.post("/transfers/{token}/claim", response_model=Booking)
async def claim_transfer(token: str, user: OnboardedUser, session: DbSession, now: Now) -> Booking:
    """Одна транзакция: исходная запись отменяется, новая создаётся на то же место."""
    peek = await session.scalar(select(TransferModel).where(TransferModel.token == token))
    if peek is None:
        raise NotFound("transfer_not_found")
    source_peek = await session.get(BookingModel, peek.booking_id)
    if source_peek is None:
        raise Conflict("expired")
    await lock_user_bookings(session, user.id)
    await lock_shift(session, source_peek.shift_id)
    transfer = await session.scalar(
        select(TransferModel).where(TransferModel.id == peek.id).with_for_update()
    )
    assert transfer is not None
    await session.refresh(transfer)
    status, source = await _transfer_state(session, transfer, now)
    if status == "taken":
        raise Conflict("seat_taken")
    if status == "expired" or source is None:
        raise Conflict("expired")
    if source.user_id == user.id:
        raise Conflict("own_transfer")
    source.status = BookingStatus.CANCELLED
    source.cancelled_at = now
    transfer.status = TransferStatus.CLAIMED
    transfer.claimed_by = user.id
    await session.flush()
    booking, created = await create_booking(
        session, user, source.shift_id, now, via_transfer_id=transfer.id, reserved_seat=True
    )
    if not created:
        raise Conflict("already_booked")
    await session.commit()
    return booking_out(booking)
