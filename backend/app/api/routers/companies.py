import uuid
from datetime import date as date_cls
from datetime import datetime, time

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deal_view import build_deals, load_viewer, parse_uuid, shift_with_org
from app.api.errors import Conflict, NotFound, Unprocessable
from app.api.routers.search import company_window, run_search
from app.api.schemas.common import TimeWindow
from app.api.schemas.deals import (
    Company,
    CompanyDeal,
    CompanyIn,
    CompanyMember,
    CompanyWindowIn,
    PickIn,
    SearchResultItem,
)
from app.auth.deps import DbSession, Now, OnboardedUser
from app.config import get_settings
from app.db.enums import BookingStatus
from app.db.models import Booking, User
from app.db.models import Company as CompanyModel
from app.db.models import CompanyMember as MemberModel
from app.domain.links import new_token, startapp_link
from app.worker.queue import enqueue

router = APIRouter(tags=["companies"])

ME_LABEL = "Ты"

async def _company_for(session: AsyncSession, user: User, company_id: str) -> CompanyModel:
    cid = parse_uuid(company_id)
    company = await session.get(CompanyModel, cid) if cid is not None else None
    if company is None or await session.get(MemberModel, (company.id, user.id)) is None:
        raise NotFound("company_not_found")
    return company

async def build_company(
    session: AsyncSession, company: CompanyModel, user: User, now: datetime
) -> Company:
    tz = get_settings().tz
    rows = await session.execute(
        select(MemberModel, User)
        .join(User, User.id == MemberModel.user_id)
        .where(MemberModel.company_id == company.id)
        .order_by(
            MemberModel.user_id != company.owner_id,
            MemberModel.joined_at,
            User.created_at,
            User.id,
        )
    )
    members = []
    names: dict[uuid.UUID, str] = {}
    for m, u in rows:
        names[u.id] = ME_LABEL if u.id == user.id else u.first_name
        window = (
            TimeWindow(from_=m.window_from, to=m.window_to)
            if m.window_from is not None and m.window_to is not None
            else None
        )
        members.append(
            CompanyMember(
                id=str(u.id),
                first_name=u.first_name,
                initial=(u.first_name[:1] or "?").upper(),
                is_me=u.id == user.id,
                window=window,
                reminded_at=m.reminded_at,
            )
        )
    common, marked = await company_window(session, company.id)
    viewer = await load_viewer(session, user)
    items: list[SearchResultItem] = []
    if common is not None:
        items, _ = await run_search(session, viewer, user, common, "campus", now, max(1, marked))
    deals = [i.deal for i in items]
    if company.picked_shift_id is not None and all(
        d.id != str(company.picked_shift_id) for d in deals
    ):
        picked = await shift_with_org(session, company.picked_shift_id)
        if picked is not None:
            deals = (await build_deals(session, [picked], viewer, now)) + deals

    votes: dict[str, list[str]] = {}
    booked = await session.execute(
        select(Booking.shift_id, Booking.user_id).where(
            Booking.company_id == company.id, Booking.status != BookingStatus.CANCELLED
        )
    )
    for sid, uid in booked:
        if uid in names:
            votes.setdefault(str(sid), []).append(names[uid])

    return Company(
        id=str(company.id),
        date=datetime.combine(company.date, time(12, 0), tzinfo=tz),
        common_window=(
            TimeWindow(from_=common.starts_at, to=common.ends_at) if common is not None else None
        ),
        members=members,
        invite_link=startapp_link("co", company.token),
        deals=[CompanyDeal(deal=d, votes=votes.get(d.id, [])) for d in deals],
        picked_deal_id=str(company.picked_shift_id) if company.picked_shift_id else None,
    )

@router.post("/companies", response_model=Company)
async def create_company(
    body: CompanyIn, user: OnboardedUser, session: DbSession, now: Now
) -> Company:
    try:
        day = date_cls.fromisoformat(body.date)
    except ValueError:
        raise Unprocessable("validation_error") from None
    company = CompanyModel(owner_id=user.id, token=new_token(), date=day)
    session.add(company)
    await session.flush()
    session.add(MemberModel(company_id=company.id, user_id=user.id, joined_at=now))
    await session.commit()
    return await build_company(session, company, user, now)

@router.post("/companies/join/{token}", response_model=Company)
async def join_company(token: str, user: OnboardedUser, session: DbSession, now: Now) -> Company:
    """Переход по co_<token>: вступить в компанию (повтор — без изменений)."""
    company = await session.scalar(select(CompanyModel).where(CompanyModel.token == token))
    if company is None:
        raise NotFound("company_not_found")
    if await session.get(MemberModel, (company.id, user.id)) is None:
        session.add(MemberModel(company_id=company.id, user_id=user.id, joined_at=now))
        await session.commit()
    return await build_company(session, company, user, now)

@router.get("/companies/{company_id}", response_model=Company)
async def get_company(
    company_id: str, user: OnboardedUser, session: DbSession, now: Now
) -> Company:
    company = await _company_for(session, user, company_id)
    return await build_company(session, company, user, now)

@router.put("/companies/{company_id}/window", response_model=Company)
async def set_window(
    company_id: str, body: CompanyWindowIn, user: OnboardedUser, session: DbSession, now: Now
) -> Company:
    company = await _company_for(session, user, company_id)
    member = await session.get(MemberModel, (company.id, user.id))
    assert member is not None
    if body.window is not None and body.window.to <= body.window.from_:
        raise Unprocessable("bad_window")
    member.window_from = body.window.from_ if body.window else None
    member.window_to = body.window.to if body.window else None
    await session.commit()
    return await build_company(session, company, user, now)

@router.post("/companies/{company_id}/members/{member_id}/remind", status_code=204)
async def remind(
    company_id: str, member_id: str, user: OnboardedUser, session: DbSession, now: Now
) -> Response:
    company = await _company_for(session, user, company_id)
    mid = parse_uuid(member_id)
    member = await session.get(MemberModel, (company.id, mid)) if mid is not None else None
    if member is None:
        raise NotFound("member_not_found")
    if member.user_id == user.id:
        raise Conflict("cannot_remind_self")
    if member.window_from is not None:
        raise Conflict("window_marked")
    member.reminded_at = now
    await enqueue(
        session,
        "notify.company_remind",
        {"company_id": str(company.id), "member_user_id": str(member.user_id)},
    )
    await session.commit()
    return Response(status_code=204)

@router.put("/companies/{company_id}/pick", response_model=Company)
async def pick(
    company_id: str, body: PickIn, user: OnboardedUser, session: DbSession, now: Now
) -> Company:
    company = await _company_for(session, user, company_id)
    if body.deal_id is None:
        company.picked_shift_id = None
    else:
        row = await shift_with_org(session, body.deal_id)
        if row is None:
            raise NotFound("deal_not_found")
        company.picked_shift_id = row[0].id
    await session.commit()
    return await build_company(session, company, user, now)
