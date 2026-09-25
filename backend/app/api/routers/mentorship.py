import uuid
from datetime import datetime

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deal_view import build_deals, load_viewer
from app.api.schemas.deals import Deal
from app.api.schemas.engagement import (
    MentorPair,
    MentorRequest,
    Mentorship,
    MentorshipPatch,
)
from app.auth.deps import DbSession, Now, OnboardedUser
from app.db.models import User
from app.domain import mentorship as domain
from app.domain.mentorship import RequestRow

router = APIRouter(prefix="/mentorship", tags=["mentorship"])

async def _deal(session: AsyncSession, row: RequestRow, viewer: User, now: datetime) -> Deal:
    [deal] = await build_deals(
        session, [(row.shift, row.org)], await load_viewer(session, viewer), now
    )
    return deal

async def build_mentorship(session: AsyncSession, user: User, now: datetime) -> Mentorship:
    view = await domain.mentorship_view(session, user, now)
    return Mentorship(
        eligible=view.eligible,
        deals_done=view.deals_done,
        deals_required=view.deals_required,
        accepting=view.accepting,
        requests=[
            MentorRequest(
                id=str(r.request.id),
                newbie_name=r.newbie_name,
                deal=await _deal(session, r, user, now),
            )
            for r in view.requests
        ],
        pairs=[
            MentorPair(
                id=str(p.request.id),
                newbie_name=p.newbie_name,
                deal_title=p.shift.title,
                starts_at=p.shift.starts_at,
            )
            for p in view.pairs
        ],
    )

@router.get("", response_model=Mentorship)
async def get_mentorship(user: OnboardedUser, session: DbSession, now: Now) -> Mentorship:
    return await build_mentorship(session, user, now)

@router.patch("", response_model=Mentorship)
async def patch_mentorship(
    body: MentorshipPatch, user: OnboardedUser, session: DbSession, now: Now
) -> Mentorship:
    await domain.set_accepting(session, user, body.accepting)
    await session.commit()
    return await build_mentorship(session, user, now)

@router.post("/requests/{request_id}/accept", response_model=Mentorship)
async def accept(
    request_id: uuid.UUID, user: OnboardedUser, session: DbSession, now: Now
) -> Mentorship:
    await domain.accept_request(session, user, request_id, now)
    await session.commit()
    return await build_mentorship(session, user, now)

@router.post("/requests/{request_id}/decline", response_model=Mentorship)
async def decline(
    request_id: uuid.UUID, user: OnboardedUser, session: DbSession, now: Now
) -> Mentorship:
    await domain.decline_request(session, user, request_id)
    await session.commit()
    return await build_mentorship(session, user, now)
