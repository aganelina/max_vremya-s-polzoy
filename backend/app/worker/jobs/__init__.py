from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

JobHandler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]

from app.bot import relay, updates  # noqa: E402 — после JobHandler
from app.worker.jobs import notifications as n  # noqa: E402

HANDLERS: dict[str, JobHandler] = {
    "notify.instructions": n.instructions,
    "notify.shift_cancelled": n.shift_cancelled,
    "notify.hours_credited": n.hours_credited,
    "notify.micro_reviewed": n.micro_reviewed,
    "notify.bank_response": n.bank_response,
    "notify.company_remind": n.company_remind,
    "notify.mentor_request": n.mentor_request,
    "notify.urgent_call": n.urgent_call,
    "notify.coord_message": n.coord_message,
    "notify.org_review": n.org_review,
    "notify.coordinator_joined": n.coordinator_joined,
    "notify.export": n.export,
    "notify.certificate": n.certificate,
    "notify.profile_deleted": n.profile_deleted,
    "notify.weekly_pick": n.weekly_pick,
    "shift.offer": n.shift_offer,
    "relay.to_coordinator": relay.relay_to_coordinator,
    "relay.to_participant": relay.relay_to_participant,
    updates.JOB_KIND: updates.handle_job,
}
