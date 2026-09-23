from datetime import datetime, timedelta

from fastapi import APIRouter, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import Forbidden, Unprocessable
from app.api.schemas.common import Dict
from app.api.schemas.profile import (
    Me,
    OnboardingIn,
    ProfilePatch,
    Roles,
    SearchParams,
    Stats,
    WeeklySearchIn,
)
from app.auth.deps import CurrentUser, DbSession, Now, OnboardedUser, active_membership
from app.config import get_settings
from app.db.enums import NotifyMode, Transport
from app.db.models import District, University, User
from app.domain.hours import user_stats

router = APIRouter(tags=["profile"])

async def build_me(session: AsyncSession, user: User, now: datetime) -> Me:
    settings = get_settings()
    university = await session.get(University, user.university_id) if user.university_id else None
    district = await session.get(District, user.district_id) if user.district_id else None
    stats = await user_stats(session, user.id, now, settings.tz)
    coordinator = await active_membership(session, user) is not None
    return Me(
        id=str(user.id),
        first_name=user.first_name,
        onboarded=user.onboarded_at is not None,
        consent_at=user.consent_at,
        university=Dict(id=university.id, name=university.name) if university else None,
        district=Dict(id=district.id, name=district.name) if district else None,
        interests=user.interests,
        transport=user.transport.value,
        notify=user.notify.value,
        pause_until=user.pause_until,
        weekly_search=(
            SearchParams.model_validate(user.weekly_search) if user.weekly_search else None
        ),
        stats=Stats(
            hours_year=stats.hours_year,
            hours_month=stats.hours_month,
            deals=stats.deals,
            streak_weeks=stats.streak_weeks,
            bank_balance=stats.bank_balance,
        ),
        roles=Roles(
            coordinator=coordinator,
            mentor_eligible=stats.deals >= settings.mentor_min_deals,
        ),
    )

async def _university(session: AsyncSession, university_id: str) -> University:
    university = await session.get(University, university_id)
    if university is None:
        raise Unprocessable("unknown_university")
    return university

async def _district(session: AsyncSession, district_id: str) -> District:
    district = await session.get(District, district_id)
    if district is None:
        raise Unprocessable("unknown_district")
    return district

@router.get("/me", response_model=Me)
async def get_me(user: CurrentUser, session: DbSession, now: Now) -> Me:
    return await build_me(session, user, now)

@router.post("/me/consent", response_model=Me)
async def give_consent(user: CurrentUser, session: DbSession, now: Now) -> Me:
    if user.consent_at is None:
        user.consent_at = now
        await session.commit()
    return await build_me(session, user, now)

@router.post("/me/onboarding", response_model=Me)
async def onboard(body: OnboardingIn, user: CurrentUser, session: DbSession, now: Now) -> Me:
    if user.consent_at is None:
        raise Forbidden("consent_required")
    user.university_id = (await _university(session, body.university_id)).id
    user.district_id = (await _district(session, body.district_id)).id
    if user.onboarded_at is None:
        user.onboarded_at = now
    await session.commit()
    return await build_me(session, user, now)

@router.patch("/me", response_model=Me)
async def update_profile(
    body: ProfilePatch, user: OnboardedUser, session: DbSession, now: Now
) -> Me:
    if body.interests is not None:
        user.interests = list(body.interests)
    if body.transport is not None:
        user.transport = Transport(body.transport)
    if body.notify is not None:
        user.notify = NotifyMode(body.notify)
        user.pause_until = (
            now + timedelta(days=get_settings().pause_days)
            if user.notify is NotifyMode.PAUSE
            else None
        )
    if body.university_id is not None:
        user.university_id = (await _university(session, body.university_id)).id
    if body.district_id is not None:
        user.district_id = (await _district(session, body.district_id)).id
    await session.commit()
    return await build_me(session, user, now)

@router.put("/me/weekly-search", status_code=204)
async def set_weekly_search(
    body: WeeklySearchIn, user: OnboardedUser, session: DbSession
) -> Response:
    user.weekly_search = (
        body.params.model_dump(mode="json", by_alias=True) if body.params is not None else None
    )
    await session.commit()
    return Response(status_code=204)
