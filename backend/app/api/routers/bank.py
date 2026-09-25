import uuid
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.engagement import AskHelpIn, HelpRequest, HourBank
from app.auth.deps import DbSession, Now, OnboardedUser
from app.db.enums import HelpStatus
from app.db.models import User
from app.domain import bank
from app.domain.bank import RequestView
from app.domain.hours import to_hours

router = APIRouter(prefix="/bank", tags=["bank"])

def _request(view: RequestView) -> HelpRequest:
    r = view.request
    status = r.status.value if r.status is not HelpStatus.CANCELLED else "closed"
    return HelpRequest(
        id=str(r.id),
        text=r.text,
        hours=to_hours(r.hours),
        when=r.when_label,
        district=bank.district_label(view.district_name),
        mine=view.mine,
        responded=view.responded,
        helper_name=view.helper_name,
        status=status,
    )

async def build_bank(session: AsyncSession, user: User, now: datetime) -> HourBank:
    view = await bank.bank_view(session, user, now)
    return HourBank(
        balance=to_hours(view.balance),
        reserved=to_hours(view.reserved),
        max_open_requests=bank.MAX_OPEN_REQUESTS,
        others=[_request(r) for r in view.others],
        mine=[_request(r) for r in view.mine],
    )

@router.get("", response_model=HourBank)
async def get_bank(user: OnboardedUser, session: DbSession, now: Now) -> HourBank:
    return await build_bank(session, user, now)

@router.put("/requests/{request_id}/response", response_model=HourBank)
async def respond(
    request_id: uuid.UUID, user: OnboardedUser, session: DbSession, now: Now
) -> HourBank:
    await bank.respond(session, user, request_id)
    await session.commit()
    return await build_bank(session, user, now)

@router.delete("/requests/{request_id}/response", response_model=HourBank)
async def withdraw(
    request_id: uuid.UUID, user: OnboardedUser, session: DbSession, now: Now
) -> HourBank:
    await bank.withdraw(session, user, request_id)
    await session.commit()
    return await build_bank(session, user, now)

@router.post("/requests", response_model=HourBank)
async def ask(body: AskHelpIn, user: OnboardedUser, session: DbSession, now: Now) -> HourBank:
    await bank.ask_help(session, user, body.text, body.hours, body.when, now)
    await session.commit()
    return await build_bank(session, user, now)

@router.post("/requests/{request_id}/received", response_model=HourBank)
async def received(
    request_id: uuid.UUID, user: OnboardedUser, session: DbSession, now: Now
) -> HourBank:
    await bank.confirm_received(session, user, request_id, now)
    await session.commit()
    return await build_bank(session, user, now)
