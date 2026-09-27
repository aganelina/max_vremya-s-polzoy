from __future__ import annotations

import base64
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import (
    Booking,
    BotConversation,
    BusySlot,
    Certificate,
    Company,
    CompanyMember,
    FreeWindow,
    FriendInvite,
    HelpRequest,
    HelpResponse,
    HourLedger,
    MaxChat,
    MentorRequest,
    MentorSettings,
    MicroAnswer,
    OrgMember,
    Schedule,
    SeatTransfer,
    User,
)

_SECTIONS: dict[str, tuple[type[Base], str]] = {
    "botConversation": (BotConversation, "user_id"),
    "maxChat": (MaxChat, "user_id"),
    "schedule": (Schedule, "user_id"),
    "busySlots": (BusySlot, "user_id"),
    "freeWindows": (FreeWindow, "user_id"),
    "bookings": (Booking, "user_id"),
    "hourLedger": (HourLedger, "user_id"),
    "microAnswers": (MicroAnswer, "user_id"),
    "helpRequests": (HelpRequest, "author_id"),
    "helpResponses": (HelpResponse, "user_id"),
    "mentorSettings": (MentorSettings, "user_id"),
    "mentorRequests": (MentorRequest, "newbie_id"),
    "companiesOwned": (Company, "owner_id"),
    "companyMemberships": (CompanyMember, "user_id"),
    "friendInvites": (FriendInvite, "inviter_id"),
    "seatTransfersClaimed": (SeatTransfer, "claimed_by"),
    "orgMemberships": (OrgMember, "user_id"),
    "certificates": (Certificate, "user_id"),
}

def _value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return base64.b64encode(value).decode()
    if isinstance(value, list):
        return [_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _value(v) for k, v in value.items()}
    return value

def row_dict(row: Base) -> dict[str, Any]:
    return {attr.key: _value(getattr(row, attr.key)) for attr in inspect(row).mapper.column_attrs}

async def export_json(session: AsyncSession, user: User) -> dict[str, Any]:
    data: dict[str, Any] = {"profile": row_dict(user)}
    for section, (model, column) in _SECTIONS.items():
        rows = await session.scalars(select(model).where(getattr(model, column) == user.id))
        data[section] = [row_dict(row) for row in rows]
    return data
