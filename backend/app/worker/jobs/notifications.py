from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import keyboards, notify
from app.bot.notify import Audience
from app.bot.relay import coordinator_text
from app.clock import current_time
from app.db.enums import (
    BookingStatus,
    HelpStatus,
    LedgerSource,
    MentorRequestStatus,
    MessageAudience,
    MicroAnswerStatus,
    NotifyMode,
    OrgRole,
    OrgStatus,
    RelayDirection,
    ShiftStatus,
)
from app.db.models import (
    Booking,
    Certificate,
    Company,
    FreeWindow,
    HelpRequest,
    HourLedger,
    MentorRequest,
    Message,
    MessageRelay,
    MicroAnswer,
    MicroTask,
    Org,
    OrgMember,
    Shift,
    UrgentCall,
    UrgentRecipient,
    User,
)
from app.domain.hours import minutes_hours
from app.worker.jobs._common import fan_out, uuid_of
from app.worker.jobs.export import export_json

log = structlog.get_logger("worker")

Payload = dict[str, Any]

OFFER_LIMIT = 200
WEEKLY_PICK_SIZE = 3
WEEKLY_PICK_HORIZON = timedelta(days=7)

_CAME = (BookingStatus.CHECKED_IN, BookingStatus.MANUAL, BookingStatus.DONE)

async def _user(session: AsyncSession, payload: Payload, key: str = "user_id") -> User | None:
    user_id = uuid_of(payload, key)
    return await session.get(User, user_id) if user_id else None

def _shift_line(shift: Shift) -> str:
    return f"«{shift.title}», {notify.fmt_when(shift.starts_at)}"

async def _seats_left(session: AsyncSession, shift: Shift) -> int:
    taken = await session.scalar(
        select(func.count())
        .select_from(Booking)
        .where(Booking.shift_id == shift.id, Booking.status != BookingStatus.CANCELLED)
    )
    return shift.capacity - int(taken or 0)

async def _is_booked(session: AsyncSession, shift_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    found = await session.scalar(
        select(Booking.id).where(
            Booking.shift_id == shift_id,
            Booking.user_id == user_id,
            Booking.status != BookingStatus.CANCELLED,
        )
    )
    return found is not None

async def instructions(session: AsyncSession, payload: Payload) -> None:
    booking_id = uuid_of(payload, "booking_id")
    booking = await session.get(Booking, booking_id) if booking_id else None
    if booking is None or booking.status != BookingStatus.GOING:
        return
    shift = await session.get(Shift, booking.shift_id)
    user = await session.get(User, booking.user_id)
    if shift is None or user is None or shift.status != ShiftStatus.OPEN:
        return
    if shift.ends_at <= current_time():
        return
    lines = [f"Напоминаю: {_shift_line(shift)}."]
    if shift.address:
        note = f" ({shift.address_note})" if shift.address_note else ""
        lines.append(f"Адрес: {shift.address}{note}")
    if shift.instructions:
        lines.append(f"Что важно знать: {shift.instructions}")
    await notify.send(
        session,
        user,
        "\n".join(lines),
        Audience.MINE,
        attachments=[
            keyboards.booking_actions(str(booking.id), str(shift.id), "my:upcoming:0", contact=True)
        ],
        kind="instructions",
    )

async def shift_cancelled(session: AsyncSession, payload: Payload) -> None:
    shift_id = uuid_of(payload, "shift_id")
    shift = await session.get(Shift, shift_id) if shift_id else None
    if shift is None:
        return
    if "user_id" not in payload:
        if isinstance(payload.get("user_ids"), list):
            parsed = (uuid_of({"id": v}, "id") for v in payload["user_ids"])
            user_ids = [u for u in parsed if u is not None]
        else:
            user_ids = await _cancelled_by_shift(session, shift)
        await fan_out(
            session,
            "notify.shift_cancelled",
            {
                "shift_id": str(shift.id),
                "reason": payload.get("reason"),
            },
            user_ids,
        )
        return
    user = await _user(session, payload)
    if user is None:
        return
    reason = (
        "не набрала команду к началу и отменена"
        if payload.get("reason") == "quorum"
        else "отменена организатором"
    )
    await notify.send(
        session,
        user,
        f"Смена {_shift_line(shift)} {reason}. Запись снята — подбери другое дело в приложении.",
        Audience.CRITICAL,
        attachments=[keyboards.open_app(keyboards.FIND_DEAL)],
        kind="shift_cancelled",
    )

async def _cancelled_by_shift(session: AsyncSession, shift: Shift) -> list[uuid.UUID]:
    last = await session.scalar(
        select(func.max(Booking.cancelled_at)).where(
            Booking.shift_id == shift.id, Booking.status == BookingStatus.CANCELLED
        )
    )
    rows = await session.scalars(
        select(Booking.user_id).where(
            Booking.shift_id == shift.id,
            (Booking.status == BookingStatus.GOING)
            | ((Booking.status == BookingStatus.CANCELLED) & (Booking.cancelled_at == last)),
        )
    )
    return list(rows)

async def hours_credited(session: AsyncSession, payload: Payload) -> None:
    booking_id = uuid_of(payload, "booking_id")
    booking = await session.get(Booking, booking_id) if booking_id else None
    if booking is None or booking.status != BookingStatus.DONE:
        return
    hours = await session.scalar(
        select(HourLedger.hours).where(
            HourLedger.user_id == booking.user_id,
            HourLedger.source == LedgerSource.SHIFT,
            HourLedger.ref_id == booking.id,
        )
    )
    shift = await session.get(Shift, booking.shift_id)
    user = await session.get(User, booking.user_id)
    if hours is None or shift is None or user is None:
        return
    await notify.send(
        session,
        user,
        f"Спасибо! «{shift.title}» засчитано: +{notify.fmt_hours(hours)} ч в справку.",
        Audience.MINE,
        kind="hours_credited",
    )

async def shift_offer(session: AsyncSession, payload: Payload) -> None:
    shift_id = uuid_of(payload, "shift_id")
    shift = await session.get(Shift, shift_id) if shift_id else None
    if shift is None or not await _offerable(session, shift):
        return
    if "user_id" not in payload:
        members = select(OrgMember.user_id).where(
            OrgMember.org_id == shift.org_id, OrgMember.revoked_at.is_(None)
        )
        booked = select(Booking.user_id).where(
            Booking.shift_id == shift.id, Booking.status != BookingStatus.CANCELLED
        )
        user_ids = await session.scalars(
            select(User.id)
            .join(FreeWindow, FreeWindow.user_id == User.id)
            .where(
                User.notify == NotifyMode.ALL,
                User.onboarded_at.is_not(None),
                FreeWindow.starts_at <= shift.starts_at,
                FreeWindow.ends_at >= shift.ends_at,
                User.id.not_in(members),
                User.id.not_in(booked),
            )
            .distinct()
            .limit(OFFER_LIMIT)
        )
        await fan_out(session, "shift.offer", {"shift_id": str(shift.id)}, list(user_ids))
        return
    user = await _user(session, payload)
    if user is None or await _is_booked(session, shift.id, user.id):
        return
    await notify.send(
        session,
        user,
        f"Нашлось дело в твоё свободное окно: {_shift_line(shift)}.",
        Audience.ALL,
        attachments=[keyboards.open_app("Посмотреть")],
        kind="shift_offer",
    )

async def _offerable(session: AsyncSession, shift: Shift) -> bool:
    org = await session.get(Org, shift.org_id)
    return (
        shift.status == ShiftStatus.OPEN
        and shift.starts_at > current_time()
        and org is not None
        and org.status == OrgStatus.VERIFIED
        and await _seats_left(session, shift) > 0
    )

async def micro_reviewed(session: AsyncSession, payload: Payload) -> None:
    answer_id = uuid_of(payload, "answer_id")
    answer = await session.get(MicroAnswer, answer_id) if answer_id else None
    if answer is None:
        return
    task = await session.get(MicroTask, answer.task_id)
    user = await session.get(User, answer.user_id)
    if task is None or user is None:
        return
    if answer.status == MicroAnswerStatus.ACCEPTED:
        hours = minutes_hours(task.minutes)
        text = f"Микро-дело «{task.title}» принято: +{notify.fmt_hours(hours)} ч. Спасибо!"
    elif answer.status == MicroAnswerStatus.RETURNED:
        note = f": {answer.review_note}" if answer.review_note else "."
        text = f"Микро-дело «{task.title}» вернули на доработку{note}"
    else:
        return
    await notify.send(
        session, user, text, Audience.MINE, attachments=[keyboards.open_app()], kind="micro"
    )

async def bank_response(session: AsyncSession, payload: Payload) -> None:
    request_id = uuid_of(payload, "request_id")
    request = await session.get(HelpRequest, request_id) if request_id else None
    helper = await _user(session, payload, "helper_id")
    if request is None or helper is None:
        return
    if request.status in (HelpStatus.CANCELLED, HelpStatus.CLOSED):
        return
    author = await session.get(User, request.author_id)
    if author is None:
        return
    await notify.send(
        session,
        author,
        f"{helper.first_name or 'Кто-то'} готов помочь с твоей просьбой в банке часов. "
        "Подробности — в приложении.",
        Audience.MINE,
        attachments=[keyboards.open_app()],
        kind="bank_response",
    )

async def company_remind(session: AsyncSession, payload: Payload) -> None:
    company_id = uuid_of(payload, "company_id")
    company = await session.get(Company, company_id) if company_id else None
    member = await _user(session, payload, "member_user_id")
    if company is None or member is None:
        return
    owner = await session.get(User, company.owner_id)
    name = owner.first_name if owner is not None and owner.first_name else "Друг"
    await notify.send(
        session,
        member,
        f"{name} зовёт тебя пойти вместе {notify.fmt_day_date(company.date)}. "
        "Отметь, когда ты свободен, — подберём дело на всех.",
        Audience.MINE,
        attachments=[keyboards.open_app("Отметить окно", f"co_{company.token}")],
        kind="company_remind",
    )

async def mentor_request(session: AsyncSession, payload: Payload) -> None:
    request_id = uuid_of(payload, "request_id")
    request = await session.get(MentorRequest, request_id) if request_id else None
    if request is None or request.status != MentorRequestStatus.OPEN or request.mentor_id is None:
        return
    mentor = await session.get(User, request.mentor_id)
    newbie = await session.get(User, request.newbie_id)
    shift = await session.get(Shift, request.shift_id)
    if mentor is None or newbie is None or shift is None or shift.starts_at <= current_time():
        return
    await notify.send(
        session,
        mentor,
        f"{newbie.first_name or 'Новичок'} впервые идёт на доброе дело: {_shift_line(shift)}. "
        "Пойдёшь наставником?",
        Audience.ALL,
        attachments=[keyboards.open_app("Ответить")],
        kind="mentor_request",
    )

async def urgent_call(session: AsyncSession, payload: Payload) -> None:
    call_id = uuid_of(payload, "call_id")
    call = await session.get(UrgentCall, call_id) if call_id else None
    if call is None:
        return
    shift = await session.get(Shift, call.shift_id)
    if shift is None or shift.status != ShiftStatus.OPEN or shift.starts_at <= current_time():
        return
    if "user_id" not in payload:
        pending = await session.scalars(
            select(UrgentRecipient.user_id).where(
                UrgentRecipient.call_id == call.id, UrgentRecipient.sent_at.is_(None)
            )
        )
        await fan_out(session, "notify.urgent_call", {"call_id": str(call.id)}, list(pending))
        return
    user = await _user(session, payload)
    recipient = await session.get(UrgentRecipient, (call.id, user.id)) if user else None
    if user is None or recipient is None or recipient.sent_at is not None:
        return
    text = (
        f"Срочно нужна помощь: {call.what}. {call.where_text}, "
        f"начало через {call.start_in_min} мин ({notify.fmt_time(shift.starts_at)}). "
        f"Нужно людей: {call.people}."
    )
    mid = await notify.send(
        session,
        user,
        text,
        Audience.ALL,
        attachments=[keyboards.urgent_go(str(call.id))],
        kind="urgent_call",
    )
    if mid is not None:
        recipient.sent_at = current_time()

async def coord_message(session: AsyncSession, payload: Payload) -> None:
    message_id = uuid_of(payload, "message_id")
    message = await session.get(Message, message_id) if message_id else None
    if message is None:
        return
    shift = await session.get(Shift, message.shift_id)
    if shift is None:
        return
    if "user_id" not in payload:
        if message.audience == MessageAudience.WAITING:
            audience = Booking.status == BookingStatus.GOING
        elif message.audience == MessageAudience.CAME:
            audience = Booking.status.in_(_CAME)
        else:
            audience = Booking.status != BookingStatus.CANCELLED
        user_ids = await session.scalars(
            select(Booking.user_id)
            .where(Booking.shift_id == shift.id, audience)
            .order_by(Booking.created_at)
        )
        await fan_out(
            session, "notify.coord_message", {"message_id": str(message.id)}, list(user_ids)
        )
        return
    user = await _user(session, payload)
    if user is None:
        return
    already = await session.scalar(
        select(MessageRelay.id).where(
            MessageRelay.message_id == message.id,
            MessageRelay.participant_id == user.id,
            MessageRelay.direction == RelayDirection.TO_PARTICIPANT,
        )
    )
    if already is not None:
        return
    mid = await notify.send(
        session, user, coordinator_text(message, shift), Audience.MINE, kind="coord_message"
    )
    if mid is not None:
        session.add(
            MessageRelay(
                message_id=message.id,
                participant_id=user.id,
                coordinator_id=message.created_by,
                participant_mid=mid,
                direction=RelayDirection.TO_PARTICIPANT,
                created_at=current_time(),
            )
        )

async def org_review(session: AsyncSession, payload: Payload) -> None:
    org_id = uuid_of(payload, "org_id")
    org = await session.get(Org, org_id) if org_id else None
    if org is None:
        return
    if org.status == OrgStatus.VERIFIED:
        text = (
            f"Организация «{org.name}» прошла проверку. "
            "Теперь можно публиковать смены и микро-дела."
        )
    elif org.status == OrgStatus.REJECTED:
        reason = f": {org.reject_reason}" if org.reject_reason else "."
        text = f"Заявка организации «{org.name}» отклонена{reason} Исправь данные и подай заново."
    else:
        return
    owners = list(
        await session.scalars(
            select(OrgMember.user_id).where(
                OrgMember.org_id == org.id,
                OrgMember.role == OrgRole.OWNER,
                OrgMember.revoked_at.is_(None),
            )
        )
    )
    if org.created_by is not None:
        owners.append(org.created_by)
    for user_id in dict.fromkeys(owners):
        user = await session.get(User, user_id)
        if user is not None:
            await notify.send(
                session,
                user,
                text,
                Audience.MINE,
                attachments=[keyboards.open_app()],
                kind="org_review",
            )

async def coordinator_joined(session: AsyncSession, payload: Payload) -> None:
    org_id = uuid_of(payload, "org_id")
    org = await session.get(Org, org_id) if org_id else None
    member = await _user(session, payload)
    if org is None or member is None:
        return
    owners = await session.scalars(
        select(OrgMember.user_id).where(
            OrgMember.org_id == org.id,
            OrgMember.role == OrgRole.OWNER,
            OrgMember.revoked_at.is_(None),
            OrgMember.user_id != member.id,
        )
    )
    text = f"{member.first_name or 'Новый участник'} стал координатором «{org.name}»."
    for user_id in list(owners):
        owner = await session.get(User, user_id)
        if owner is not None:
            await notify.send(
                session,
                owner,
                text,
                Audience.MINE,
                attachments=[keyboards.open_app()],
                kind="coordinator_joined",
            )

async def export(session: AsyncSession, payload: Payload) -> None:
    user = await _user(session, payload)
    if user is None:
        return
    data = await export_json(session, user)
    await notify.send_file(
        session,
        user,
        json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
        "vremya-export.json",
        "Все твои данные в «Время с пользой» — в этом файле.",
        kind="export",
    )

async def certificate_pdf(session: AsyncSession, certificate: Certificate) -> bytes:
    from app.domain.certificate import certificate_pdf as render

    return await render(session, certificate.id)

async def certificate(session: AsyncSession, payload: Payload) -> None:
    certificate_id = uuid_of(payload, "certificate_id")
    cert = await session.get(Certificate, certificate_id) if certificate_id else None
    if cert is None or cert.revoked_at is not None or cert.user_id is None:
        return
    user = await session.get(User, cert.user_id)
    if user is None:
        return
    pdf = await certificate_pdf(session, cert)
    await notify.send_file(
        session,
        user,
        pdf,
        f"spravka-{cert.code}.pdf",
        f"Справка о волонтёрских часах. Код подлинности: {cert.code}",
        kind="certificate",
    )

async def profile_deleted(session: AsyncSession, payload: Payload) -> None:
    try:
        chat_id = int(payload["chat_id"])
    except (KeyError, TypeError, ValueError):
        return
    await notify.send_to_chat(
        chat_id,
        "Профиль удалён: все данные стёрты, справки аннулированы. "
        "Захочешь вернуться — нажми /start.",
        kind="profile_deleted",
    )

async def weekly_pick(session: AsyncSession, payload: Payload) -> None:
    user = await _user(session, payload)
    if user is None or not user.weekly_search:
        return
    if not notify.allowed(user, Audience.ALL):
        return
    shifts = await pick_for_week(session, user)
    if not shifts:
        return
    lines = ["Подборка недели под твои сохранённые параметры:"]
    lines += [f"• {_shift_line(shift)}" for shift in shifts]
    await notify.send(
        session,
        user,
        "\n".join(lines),
        Audience.ALL,
        attachments=[keyboards.open_app(keyboards.FIND_DEAL)],
        kind="weekly_pick",
    )

async def pick_for_week(session: AsyncSession, user: User) -> list[Shift]:
    now = current_time()
    params = user.weekly_search or {}
    if params.get("durationMin") and params.get("when"):
        from app.api.deal_view import load_viewer
        from app.api.routers.search import resolve_window, run_search

        window, _ = await resolve_window(
            session,
            user,
            duration_min=int(params["durationMin"]),
            when=str(params["when"]),
            now=now,
        )
        items, _ = await run_search(
            session,
            await load_viewer(session, user),
            user,
            window,
            str(params.get("from", "campus")),
            now,
        )
        ids = [uuid.UUID(i.deal.id) for i in items]
        shifts = {s.id: s for s in await session.scalars(select(Shift).where(Shift.id.in_(ids)))}
        ranked = sorted(
            (shifts[i] for i in ids if i in shifts),
            key=lambda s: s.category.value not in (user.interests or []),
        )
        return ranked[:WEEKLY_PICK_SIZE]
    taken = (
        select(func.count())
        .select_from(Booking)
        .where(Booking.shift_id == Shift.id, Booking.status != BookingStatus.CANCELLED)
        .correlate(Shift)
        .scalar_subquery()
    )
    mine = select(Booking.shift_id).where(
        Booking.user_id == user.id, Booking.status != BookingStatus.CANCELLED
    )
    query = (
        select(Shift)
        .join(Org, Org.id == Shift.org_id)
        .where(
            Shift.status == ShiftStatus.OPEN,
            Org.status == OrgStatus.VERIFIED,
            Shift.starts_at > now,
            Shift.starts_at <= now + WEEKLY_PICK_HORIZON,
            taken < Shift.capacity,
            Shift.id.not_in(mine),
        )
        .order_by(Shift.starts_at)
        .limit(WEEKLY_PICK_SIZE)
    )
    if user.interests:
        query = query.where(Shift.category.in_(user.interests))
    return list(await session.scalars(query))
