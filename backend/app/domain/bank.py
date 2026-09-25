import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.errors import Conflict, NotFound
from app.config import get_settings
from app.db.enums import HelpStatus, LedgerSource
from app.db.models import District, HelpRequest, HelpResponse, HourLedger, User
from app.domain.hours import user_stats
from app.worker.queue import enqueue

MAX_OPEN_REQUESTS = 3
DEFAULT_WHEN = "когда удобно"
ACTIVE_STATUSES = (HelpStatus.OPEN, HelpStatus.MATCHED)

def district_label(name: str | None) -> str:
    return f"{name} район" if name else ""

def check_can_ask(open_count: int, hours: Decimal, available: Decimal) -> None:
    if open_count >= MAX_OPEN_REQUESTS:
        raise Conflict("too_many_requests")
    if hours > available:
        raise Conflict("insufficient_balance")

async def balance(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> Decimal:
    stats = await user_stats(session, user_id, now, get_settings().tz)
    return Decimal(str(stats.bank_balance))

async def reserved(session: AsyncSession, user_id: uuid.UUID) -> Decimal:
    total = await session.scalar(
        select(func.coalesce(func.sum(HelpRequest.hours), 0)).where(
            HelpRequest.author_id == user_id, HelpRequest.status.in_(ACTIVE_STATUSES)
        )
    )
    return Decimal(str(total or 0))

async def lock_author(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())

@dataclass(frozen=True)
class RequestView:
    request: HelpRequest
    district_name: str | None
    mine: bool
    responded: bool
    helper_name: str | None

@dataclass(frozen=True)
class BankView:
    balance: Decimal
    reserved: Decimal
    others: list[RequestView]
    mine: list[RequestView]

async def bank_view(session: AsyncSession, user: User, now: datetime) -> BankView:
    responded_ids = set(
        (
            await session.scalars(
                select(HelpResponse.request_id).where(HelpResponse.user_id == user.id)
            )
        ).all()
    )
    others: list[RequestView] = []
    if user.district_id is not None:
        rows = (
            await session.execute(
                select(HelpRequest, District.name)
                .outerjoin(District, District.id == HelpRequest.district_id)
                .where(
                    HelpRequest.district_id == user.district_id,
                    HelpRequest.author_id != user.id,
                    or_(
                        HelpRequest.status == HelpStatus.OPEN,
                        (HelpRequest.status == HelpStatus.MATCHED)
                        & HelpRequest.id.in_(responded_ids),
                    ),
                )
                .order_by(HelpRequest.created_at.desc())
            )
        ).all()
        others = [
            RequestView(r, name, mine=False, responded=r.id in responded_ids, helper_name=None)
            for r, name in rows
        ]
    helper = aliased(User, name="helper")
    mine_rows = (
        await session.execute(
            select(HelpRequest, District.name, helper.first_name)
            .outerjoin(District, District.id == HelpRequest.district_id)
            .outerjoin(helper, helper.id == HelpRequest.helper_id)
            .where(HelpRequest.author_id == user.id, HelpRequest.status != HelpStatus.CANCELLED)
            .order_by(HelpRequest.created_at.desc())
        )
    ).all()
    mine = [
        RequestView(
            r,
            name,
            mine=True,
            responded=r.helper_id is not None,
            helper_name=helper_name,
        )
        for r, name, helper_name in mine_rows
    ]
    return BankView(
        balance=await balance(session, user.id, now),
        reserved=await reserved(session, user.id),
        others=others,
        mine=mine,
    )

async def ask_help(
    session: AsyncSession, user: User, text: str, hours: Decimal, when: str | None, now: datetime
) -> HelpRequest:
    await lock_author(session, user.id)
    open_count = await session.scalar(
        select(func.count())
        .select_from(HelpRequest)
        .where(HelpRequest.author_id == user.id, HelpRequest.status.in_(ACTIVE_STATUSES))
    )
    available = await balance(session, user.id, now) - await reserved(session, user.id)
    check_can_ask(int(open_count or 0), hours, available)
    request = HelpRequest(
        author_id=user.id,
        text=text,
        hours=hours,
        when_label=when or DEFAULT_WHEN,
        district_id=user.district_id,
        status=HelpStatus.OPEN,
    )
    session.add(request)
    await session.flush()
    return request

async def _locked(session: AsyncSession, request_id: uuid.UUID) -> HelpRequest:
    request = await session.scalar(
        select(HelpRequest).where(HelpRequest.id == request_id).with_for_update()
    )
    if request is None or request.status is HelpStatus.CANCELLED:
        raise NotFound()
    return request

async def respond(session: AsyncSession, user: User, request_id: uuid.UUID) -> None:
    request = await _locked(session, request_id)
    if request.author_id == user.id or request.district_id != user.district_id:
        raise NotFound()
    if request.status is HelpStatus.CLOSED:
        raise Conflict("request_closed")
    inserted = (
        await session.execute(
            pg_insert(HelpResponse)
            .values(request_id=request.id, user_id=user.id)
            .on_conflict_do_nothing()
            .returning(HelpResponse.user_id)
        )
    ).first()
    if inserted is None:
        return
    if request.helper_id is None:
        request.helper_id = user.id
        request.status = HelpStatus.MATCHED
    await enqueue(
        session,
        "notify.bank_response",
        {"request_id": str(request.id), "helper_id": str(user.id)},
    )
    await session.flush()

async def withdraw(session: AsyncSession, user: User, request_id: uuid.UUID) -> None:
    request = await _locked(session, request_id)
    if request.author_id == user.id:
        raise NotFound()
    if request.status is HelpStatus.CLOSED:
        raise Conflict("request_closed")
    await session.execute(
        delete(HelpResponse).where(
            HelpResponse.request_id == request.id, HelpResponse.user_id == user.id
        )
    )
    if request.helper_id == user.id:
        next_helper = await session.scalar(
            select(HelpResponse.user_id)
            .where(HelpResponse.request_id == request.id)
            .order_by(HelpResponse.created_at)
            .limit(1)
        )
        request.helper_id = next_helper
        request.status = HelpStatus.MATCHED if next_helper else HelpStatus.OPEN
    await session.flush()

async def confirm_received(
    session: AsyncSession, user: User, request_id: uuid.UUID, now: datetime
) -> None:
    request = await _locked(session, request_id)
    if request.author_id != user.id:
        raise NotFound()
    if request.status is HelpStatus.CLOSED:
        return
    if request.helper_id is None:
        raise Conflict("no_helper")
    await lock_author(session, user.id)
    if await balance(session, user.id, now) < request.hours:
        raise Conflict("insufficient_balance")
    request.status = HelpStatus.CLOSED
    session.add_all(
        [
            HourLedger(
                user_id=user.id,
                source=LedgerSource.BANK_SPEND,
                ref_id=request.id,
                hours=-request.hours,
                accepted_at=now,
            ),
            HourLedger(
                user_id=request.helper_id,
                source=LedgerSource.BANK_HELP,
                ref_id=request.id,
                hours=request.hours,
                accepted_at=now,
            ),
        ]
    )
    await session.flush()
