import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

import structlog
from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import ApiError, Forbidden
from app.api.throttle import user_limiter
from app.auth.init_data import InitDataError, InitDataErrorReason, validate_init_data
from app.auth.users import upsert_user
from app.clock import current_time
from app.config import get_settings
from app.db.enums import OrgRole, OrgStatus
from app.db.models import Org, OrgMember, User
from app.db.session import get_session

log = structlog.get_logger("auth")

DbSession = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[datetime, Depends(current_time)]

INIT_DATA_HEADER = "X-Max-Init-Data"
DEV_USER_HEADER = "X-Dev-User"

def _test_account(authorization: str) -> int | None:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    found = None
    for known, max_user_id in get_settings().test_account_pairs():
        if hmac.compare_digest(known.encode(), token.strip().encode()):
            found = max_user_id
    return found

class Unauthorized(ApiError):
    def __init__(self, code: str = "init_data_invalid") -> None:
        super().__init__(401, code)

async def current_user(
    session: DbSession,
    now: Now,
    init_data: Annotated[str | None, Header(alias=INIT_DATA_HEADER)] = None,
    dev_user: Annotated[str | None, Header(alias=DEV_USER_HEADER)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    settings = get_settings()
    test_user = _test_account(authorization) if authorization else None
    if test_user is not None:
        user = await session.scalar(select(User).where(User.max_user_id == test_user))
        if user is None:
            raise Unauthorized("test_account_unknown")
    elif init_data:
        if not settings.max_bot_token:
            raise Unauthorized()
        try:
            data = validate_init_data(
                init_data,
                settings.max_bot_token,
                max_age=settings.init_data_max_age_seconds,
                clock_skew=settings.init_data_clock_skew_seconds,
                now=now,
            )
        except InitDataError as exc:
            log.info("init_data_rejected", reason=exc.reason.value)
            if exc.reason is InitDataErrorReason.EXPIRED:
                raise Unauthorized("init_data_expired") from None
            raise Unauthorized() from None
        user = await upsert_user(session, data.user_id, data.first_name)
    elif dev_user and settings.dev_auth_enabled:
        try:
            max_user_id = int(dev_user)
        except ValueError:
            raise Unauthorized() from None
        user = await upsert_user(session, max_user_id, None)
    else:
        raise Unauthorized()
    await session.commit()
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    user_limiter.hit(str(user.id))
    return user

CurrentUser = Annotated[User, Depends(current_user)]

def is_onboarded(user: User) -> bool:
    return user.consent_at is not None and user.onboarded_at is not None

async def onboarded_user(user: CurrentUser) -> User:
    if not is_onboarded(user):
        raise Forbidden("onboarding_required")
    return user

OnboardedUser = Annotated[User, Depends(onboarded_user)]

@dataclass(frozen=True)
class CoordinatorContext:
    user: User
    org: Org
    role: OrgRole

    @property
    def is_owner(self) -> bool:
        return self.role is OrgRole.OWNER

async def active_membership(session: AsyncSession, user: User) -> tuple[OrgMember, Org] | None:
    row = (
        await session.execute(
            select(OrgMember, Org)
            .join(Org, Org.id == OrgMember.org_id)
            .where(
                OrgMember.user_id == user.id,
                OrgMember.revoked_at.is_(None),
                Org.status == OrgStatus.VERIFIED,
            )
            .order_by(OrgMember.created_at, Org.id)
            .limit(1)
        )
    ).first()
    return None if row is None else (row[0], row[1])

async def require_coordinator(user: OnboardedUser, session: DbSession) -> CoordinatorContext:
    found = await active_membership(session, user)
    if found is None:
        raise Forbidden("not_coordinator")
    member, org = found
    return CoordinatorContext(user=user, org=org, role=member.role)

Coordinator = Annotated[CoordinatorContext, Depends(require_coordinator)]

async def require_operator(user: OnboardedUser) -> User:
    if not user.is_operator:
        raise Forbidden("not_operator")
    return user

Operator = Annotated[User, Depends(require_operator)]
