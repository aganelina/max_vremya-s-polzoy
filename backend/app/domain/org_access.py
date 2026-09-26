import secrets
import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.enums import OrgRole, OrgStatus
from app.db.models import Org, OrgInvite, OrgMember, User
from app.domain.coord import INVITE_TTL, CoordError
from app.worker.queue import enqueue

INVITE_PREFIX = "org_"

def new_token() -> str:
    return secrets.token_urlsafe(16)

def invite_link(token: str) -> str:
    bot = get_settings().max_bot_username or "vremya_bot"
    return f"https://max.ru/{bot}?startapp={INVITE_PREFIX}{token}"

async def active_invite(
    session: AsyncSession, org_id: uuid.UUID, now: datetime
) -> OrgInvite | None:
    return await session.scalar(
        select(OrgInvite)
        .where(
            OrgInvite.org_id == org_id,
            OrgInvite.used_at.is_(None),
            OrgInvite.expires_at > now,
        )
        .order_by(OrgInvite.created_at.desc())
        .limit(1)
    )

async def create_invite(
    session: AsyncSession, org_id: uuid.UUID, created_by: uuid.UUID, now: datetime
) -> OrgInvite:
    invite = OrgInvite(
        org_id=org_id,
        token=new_token(),
        expires_at=now + INVITE_TTL,
        created_by=created_by,
        created_at=now,
    )
    session.add(invite)
    await session.flush()
    return invite

async def accept_org_invite(session: AsyncSession, token: str, user: User, now: datetime) -> Org:
    token = token.removeprefix(INVITE_PREFIX)
    invite = await session.scalar(
        select(OrgInvite).where(OrgInvite.token == token).with_for_update()
    )
    if invite is None:
        raise CoordError(404, "invite_not_found")
    if invite.used_at is not None:
        raise CoordError(409, "invite_used")
    if invite.expires_at <= now:
        raise CoordError(410, "invite_expired")
    org = await session.get(Org, invite.org_id)
    if org is None:
        raise CoordError(404, "invite_not_found")
    if org.status is not OrgStatus.VERIFIED:
        raise CoordError(409, "org_not_verified")
    existing = await session.get(OrgMember, (org.id, user.id))
    if existing is not None and existing.revoked_at is not None:
        raise CoordError(409, "member_revoked")
    joined = await session.scalar(
        pg_insert(OrgMember)
        .values(org_id=org.id, user_id=user.id, role=OrgRole.COORDINATOR)
        .on_conflict_do_nothing(index_elements=[OrgMember.org_id, OrgMember.user_id])
        .returning(OrgMember.user_id)
    )
    invite.used_at = now
    if joined is not None:
        await enqueue(
            session, "notify.coordinator_joined", {"org_id": str(org.id), "user_id": str(user.id)}
        )
    await session.flush()
    return org

async def set_revoked(
    session: AsyncSession,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    member_user_id: uuid.UUID,
    revoked: bool,
    now: datetime,
) -> None:
    if member_user_id == actor_id:
        raise CoordError(409, "cannot_revoke_self")
    member = await session.get(OrgMember, (org_id, member_user_id))
    if member is None:
        raise CoordError(404, "not_found")
    if revoked and member.revoked_at is None:
        member.revoked_at = now
        await session.execute(
            update(OrgInvite)
            .where(
                OrgInvite.org_id == org_id,
                OrgInvite.used_at.is_(None),
                OrgInvite.expires_at > now,
            )
            .values(expires_at=now)
        )
    elif not revoked:
        member.revoked_at = None
    await session.flush()

async def transfer_ownership(
    session: AsyncSession, org_id: uuid.UUID, owner_id: uuid.UUID, member_user_id: uuid.UUID
) -> None:
    if member_user_id == owner_id:
        raise CoordError(409, "cannot_transfer_to_self")
    member = await session.get(OrgMember, (org_id, member_user_id), with_for_update=True)
    if member is None or member.revoked_at is not None:
        raise CoordError(404, "member_not_found")
    owner = await session.get(OrgMember, (org_id, owner_id), with_for_update=True)
    assert owner is not None
    member.role = OrgRole.OWNER
    owner.role = OrgRole.COORDINATOR
    await session.flush()
