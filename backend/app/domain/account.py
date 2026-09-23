import hashlib
import hmac
import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, Text, and_, cast, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.enums import OrgRole, OrgStatus
from app.db.models import (
    AccountTombstone,
    Booking,
    Certificate,
    Company,
    HourLedger,
    Job,
    MaxChat,
    MessageRelay,
    Org,
    OrgMember,
    User,
)


async def sole_owned_orgs(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    owned = (
        select(OrgMember.org_id)
        .join(Org, Org.id == OrgMember.org_id)
        .where(
            OrgMember.user_id == user_id,
            OrgMember.role == OrgRole.OWNER,
            OrgMember.revoked_at.is_(None),
            Org.status == OrgStatus.VERIFIED,
        )
    )
    other_owners = (
        select(OrgMember.org_id, func.count().label("n"))
        .where(
            OrgMember.org_id.in_(owned),
            OrgMember.user_id != user_id,
            OrgMember.role == OrgRole.OWNER,
            OrgMember.revoked_at.is_(None),
        )
        .group_by(OrgMember.org_id)
    )
    with_others = {oid for oid, _ in (await session.execute(other_owners))}
    return [oid for oid in await session.scalars(owned) if oid not in with_others]

_DEV_ACCOUNT_KEY = b"vremya-dev-account-tombstones"

def account_key(max_user_id: int) -> str:
    token = get_settings().max_bot_token
    key = hashlib.sha256(b"account\x00" + token.encode()).digest() if token else _DEV_ACCOUNT_KEY
    return hmac.new(key, str(max_user_id).encode(), hashlib.sha256).hexdigest()

def account_lock_key(max_user_id: int) -> int:
    digest = hashlib.sha256(b"account-lock\x00" + str(max_user_id).encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)

async def lock_account(session: AsyncSession, max_user_id: int) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"), {"key": account_lock_key(max_user_id)}
    )

def _user_update_filter(max_user_id: int) -> ColumnElement[bool]:
    patterns = (
        {"update": {"user": {"user_id": max_user_id}}},
        {"update": {"message": {"sender": {"user_id": max_user_id}}}},
        {"update": {"callback": {"user": {"user_id": max_user_id}}}},
    )
    return or_(*(Job.payload.contains(p) for p in patterns))

async def erase_user(session: AsyncSession, user: User, now: datetime) -> int | None:
    await lock_account(session, user.max_user_id)
    chat = await session.get(MaxChat, user.id)
    chat_id = chat.chat_id if chat is not None else None
    relays = select(cast(MessageRelay.id, Text)).where(
        or_(MessageRelay.participant_id == user.id, MessageRelay.coordinator_id == user.id)
    )
    free_ids = (
        await session.scalars(
            select(Job.id)
            .where(
                or_(
                    and_(Job.kind == "bot.update", _user_update_filter(user.max_user_id)),
                    and_(
                        Job.kind.in_(("relay.to_coordinator", "relay.to_participant")),
                        Job.payload["relay_id"].astext.in_(relays),
                    ),
                )
            )
            .with_for_update(skip_locked=True)
        )
    ).all()
    if free_ids:
        await session.execute(delete(Job).where(Job.id.in_(free_ids)))
    await session.execute(
        pg_insert(AccountTombstone)
        .values(max_user_key=account_key(user.max_user_id), deleted_at=now)
        .on_conflict_do_update(
            index_elements=[AccountTombstone.max_user_key], set_={"deleted_at": now}
        )
    )
    await session.execute(
        update(Certificate)
        .where(Certificate.user_id == user.id, Certificate.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    applications = select(OrgMember.org_id).where(
        OrgMember.user_id == user.id, OrgMember.role == OrgRole.OWNER
    )
    await session.execute(
        delete(Org).where(Org.id.in_(applications), Org.status != OrgStatus.VERIFIED)
    )
    await session.execute(delete(Company).where(Company.owner_id == user.id))
    await session.execute(delete(HourLedger).where(HourLedger.user_id == user.id))
    await session.execute(delete(Booking).where(Booking.user_id == user.id))
    await session.execute(delete(User).where(User.id == user.id))
    return chat_id
