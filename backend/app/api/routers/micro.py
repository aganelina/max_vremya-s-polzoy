import uuid

from fastapi import APIRouter, Response

from app.api.schemas.engagement import MicroAnswerIn, MicroTask, Org
from app.auth.deps import DbSession, Now, OnboardedUser
from app.db.enums import MicroAnswerStatus, OrgStatus
from app.domain import micro
from app.domain.micro import MicroView

router = APIRouter(prefix="/micro-tasks", tags=["micro"])

def to_schema(view: MicroView) -> MicroTask:
    answer = view.answer
    status = "free" if answer is None else answer.status.value
    in_work = answer is not None and answer.status in micro.IN_WORK_STATUSES
    return MicroTask(
        id=str(view.task.id),
        title=view.task.title,
        org=Org(
            id=str(view.org.id),
            name=view.org.name,
            verified=view.org.status is OrgStatus.VERIFIED,
        ),
        minutes=view.task.minutes,
        text=view.task.text,
        status="free" if status == MicroAnswerStatus.RELEASED.value else status,
        deadline=answer.deadline if answer is not None and in_work else None,
        answer=answer.answer if answer is not None else "",
        review_note=(
            answer.review_note
            if answer is not None and answer.status is MicroAnswerStatus.RETURNED
            else None
        ),
    )

@router.get("/next", response_model=MicroTask)
async def next_task(
    user: OnboardedUser, session: DbSession, now: Now, skip: uuid.UUID | None = None
) -> MicroTask:
    view = await micro.next_task(session, user.id, now, skip)
    await session.commit()
    return to_schema(view)

@router.post("/{task_id}/take", response_model=MicroTask)
async def take(task_id: uuid.UUID, user: OnboardedUser, session: DbSession, now: Now) -> MicroTask:
    view = await micro.take_task(session, user.id, task_id, now)
    await session.commit()
    return to_schema(view)

@router.post("/{task_id}/answer", response_model=MicroTask)
async def answer(
    task_id: uuid.UUID, body: MicroAnswerIn, user: OnboardedUser, session: DbSession, now: Now
) -> MicroTask:
    view = await micro.submit_answer(session, user.id, task_id, body.answer, now)
    await session.commit()
    return to_schema(view)

@router.delete("/{task_id}/take", status_code=204)
async def release(task_id: uuid.UUID, user: OnboardedUser, session: DbSession) -> Response:
    await micro.release_task(session, user.id, task_id)
    await session.commit()
    return Response(status_code=204)
