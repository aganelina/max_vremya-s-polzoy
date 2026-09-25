import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import LedgerSource
from app.db.models import Booking, HourLedger, MicroAnswer, MicroTask, Org, Shift
from app.domain.hours import CREDITED_SOURCES


@dataclass(frozen=True)
class CreditRow:
    id: uuid.UUID
    date: datetime
    title: str
    org_id: uuid.UUID | None
    org_name: str
    hours: Decimal
    micro: bool

async def credited_rows(
    session: AsyncSession, user_id: uuid.UUID, since: datetime | None = None
) -> list[CreditRow]:
    q = (
        select(HourLedger, Shift, MicroTask, Org)
        .outerjoin(
            Booking,
            (HourLedger.source == LedgerSource.SHIFT) & (Booking.id == HourLedger.ref_id),
        )
        .outerjoin(Shift, Shift.id == Booking.shift_id)
        .outerjoin(
            MicroAnswer,
            (HourLedger.source == LedgerSource.MICRO) & (MicroAnswer.id == HourLedger.ref_id),
        )
        .outerjoin(MicroTask, MicroTask.id == MicroAnswer.task_id)
        .outerjoin(Org, Org.id == HourLedger.org_id)
        .where(HourLedger.user_id == user_id, HourLedger.source.in_(CREDITED_SOURCES))
    )
    if since is not None:
        q = q.where(HourLedger.accepted_at >= since)
    rows: list[CreditRow] = []
    for entry, shift, task, org in await session.execute(q):
        micro = entry.source is LedgerSource.MICRO
        if shift is not None:
            title, date = shift.title, shift.starts_at
        elif task is not None:
            title, date = task.title, entry.accepted_at
        else:
            title = "Микро-дело" if micro else "Доброе дело"
            date = entry.accepted_at
        rows.append(
            CreditRow(
                id=entry.id,
                date=date,
                title=title,
                org_id=org.id if org is not None else None,
                org_name=org.name if org is not None else "",
                hours=entry.hours,
                micro=micro,
            )
        )
    rows.sort(key=lambda r: (r.date, str(r.id)), reverse=True)
    return rows
