import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import Conflict, NotFound, Unprocessable
from app.db.enums import MicroAnswerStatus, OrgStatus
from app.db.models import MicroAnswer, MicroTask, Org

TAKE_DURATION = timedelta(hours=2)
MIN_ANSWER_LEN = 10
COUNTED_STATUSES = (
    MicroAnswerStatus.TAKEN,
    MicroAnswerStatus.SENT,
    MicroAnswerStatus.ACCEPTED,
    MicroAnswerStatus.RETURNED,
)
IN_WORK_STATUSES = (MicroAnswerStatus.TAKEN, MicroAnswerStatus.RETURNED)

def pick_next[T](candidates: Sequence[T], skip: T | None) -> T | None:
    if not candidates:
        return None
    if skip is None or skip not in candidates:
        return candidates[0]
    if len(candidates) == 1:
        return candidates[0]
    return candidates[(candidates.index(skip) + 1) % len(candidates)]

def normalize_answer(text: str) -> str:
    answer = text.strip()
    if len(answer) < MIN_ANSWER_LEN:
        raise Unprocessable("answer_too_short")
    return answer

def is_taken(answer: MicroAnswer) -> bool:
    return answer.status is MicroAnswerStatus.TAKEN

@dataclass(frozen=True)
class MicroView:
    task: MicroTask
    org: Org
    answer: MicroAnswer | None

def _available_tasks(now: datetime) -> Select[MicroTask, Org]:
    counted = (
        select(func.count())
        .select_from(MicroAnswer)
        .where(MicroAnswer.task_id == MicroTask.id, MicroAnswer.status.in_(COUNTED_STATUSES))
        .correlate(MicroTask)
        .scalar_subquery()
    )
    return (
        select(MicroTask, Org)
        .join(Org, Org.id == MicroTask.org_id)
        .where(
            MicroTask.active.is_(True),
            Org.status == OrgStatus.VERIFIED,
            or_(MicroTask.deadline_at.is_(None), MicroTask.deadline_at > now),
            counted < MicroTask.answers_needed,
        )
    )

async def _release_expired(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(MicroAnswer)
        .where(
            MicroAnswer.user_id == user_id,
            MicroAnswer.status == MicroAnswerStatus.TAKEN,
            MicroAnswer.deadline <= now,
        )
        .values(status=MicroAnswerStatus.RELEASED)
    )

async def _in_work(session: AsyncSession, user_id: uuid.UUID) -> MicroView | None:
    row = (
        await session.execute(
            select(MicroAnswer, MicroTask, Org)
            .join(MicroTask, MicroTask.id == MicroAnswer.task_id)
            .join(Org, Org.id == MicroTask.org_id)
            .where(MicroAnswer.user_id == user_id, MicroAnswer.status.in_(IN_WORK_STATUSES))
            .order_by(MicroAnswer.status, MicroAnswer.created_at)
            .limit(1)
        )
    ).first()
    return None if row is None else MicroView(task=row[1], org=row[2], answer=row[0])

async def next_task(
    session: AsyncSession, user_id: uuid.UUID, now: datetime, skip: uuid.UUID | None
) -> MicroView:
    await _release_expired(session, user_id, now)
    current = await _in_work(session, user_id)
    if current is not None:
        return current
    tried = select(MicroAnswer.task_id).where(MicroAnswer.user_id == user_id)
    rows = (
        await session.execute(
            _available_tasks(now)
            .where(MicroTask.id.not_in(tried))
            .order_by(MicroTask.created_at, MicroTask.id)
        )
    ).all()
    candidates = [row[0].id for row in rows]
    picked = pick_next(candidates, skip)
    if picked is None:
        raise NotFound("no_micro_tasks")
    task, org = next((row[0], row[1]) for row in rows if row[0].id == picked)
    return MicroView(task=task, org=org, answer=None)

async def take_task(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, now: datetime
) -> MicroView:
    await _release_expired(session, user_id, now)
    current = await _in_work(session, user_id)
    if current is not None and current.task.id == task_id:
        return current
    if current is not None and current.answer is not None and is_taken(current.answer):
        raise Conflict("already_taken")
    row = (
        await session.execute(
            select(MicroTask, Org)
            .join(Org, Org.id == MicroTask.org_id)
            .where(MicroTask.id == task_id)
            .with_for_update(of=MicroTask)
        )
    ).first()
    if row is None:
        raise NotFound()
    task, org = row[0], row[1]
    counted = await session.scalar(
        select(func.count())
        .select_from(MicroAnswer)
        .where(MicroAnswer.task_id == task.id, MicroAnswer.status.in_(COUNTED_STATUSES))
    )
    if not (
        task.active
        and org.status is OrgStatus.VERIFIED
        and (task.deadline_at is None or task.deadline_at > now)
        and int(counted or 0) < task.answers_needed
    ):
        raise Conflict("already_taken")
    answered = await session.scalar(
        select(func.count())
        .select_from(MicroAnswer)
        .where(
            MicroAnswer.task_id == task_id,
            MicroAnswer.user_id == user_id,
            MicroAnswer.status.in_(
                (MicroAnswerStatus.SENT, MicroAnswerStatus.ACCEPTED, MicroAnswerStatus.RETURNED)
            ),
        )
    )
    if answered:
        raise Conflict("already_answered")
    answer = MicroAnswer(
        task_id=task.id,
        user_id=user_id,
        status=MicroAnswerStatus.TAKEN,
        answer="",
        deadline=now + TAKE_DURATION,
    )
    session.add(answer)
    try:
        await session.flush()
    except IntegrityError:
        raise Conflict("already_taken") from None
    return MicroView(task=task, org=org, answer=answer)

async def _my_answer(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID
) -> tuple[MicroAnswer, MicroTask, Org]:
    row = (
        await session.execute(
            select(MicroAnswer, MicroTask, Org)
            .join(MicroTask, MicroTask.id == MicroAnswer.task_id)
            .join(Org, Org.id == MicroTask.org_id)
            .where(
                MicroAnswer.user_id == user_id,
                MicroAnswer.task_id == task_id,
                MicroAnswer.status.in_(IN_WORK_STATUSES),
            )
            .with_for_update(of=MicroAnswer)
        )
    ).first()
    if row is None:
        raise Conflict("not_taken")
    return row[0], row[1], row[2]

async def submit_answer(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID, text: str, now: datetime
) -> MicroView:
    answer_text = normalize_answer(text)
    await _release_expired(session, user_id, now)
    answer, task, org = await _my_answer(session, user_id, task_id)
    answer.status = MicroAnswerStatus.SENT
    answer.answer = answer_text
    await session.flush()
    return MicroView(task=task, org=org, answer=answer)

async def release_task(session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> None:
    try:
        answer, _, _ = await _my_answer(session, user_id, task_id)
    except Conflict:
        raise NotFound() from None
    answer.status = MicroAnswerStatus.RELEASED
    await session.flush()
