from __future__ import annotations

import uuid
from datetime import timedelta

from maxapi.types.attachments.buttons import CallbackButton
from sqlalchemy import and_, not_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.users import upsert_user
from app.bot import keyboards, notify
from app.bot.transport import OutgoingAttachment
from app.clock import current_time
from app.db import session as db
from app.db.enums import BookingStatus, MessageAudience, OrgStatus, RelayDirection, ShiftStatus
from app.db.models import (
    Booking,
    BotConversation,
    MaxChat,
    Message,
    MessageRelay,
    Org,
    OrgMember,
    Shift,
    User,
)

HELP = (
    "Здесь, в MAX, я напомню о смене и пришлю инструкции, сообщу об отмене и начислении "
    "часов, доставлю справку и передам вопросы координатору. "
    "На срочный вызов можно записаться кнопкой «Иду» прямо в чате.\n\n"
    "/my — записи, история и инструкции\n"
    "/messages — выбрать смену и написать координатору\n"
    "/back — вернуться в меню\n"
    "/cancel — завершить текущий диалог\n"
    "/help — это меню\n\n"
    "Координатор отвечает через «Ответить» на сообщение участника. "
    "Телефоны и личные профили друг другу не раскрываются."
)
NO_BOOKINGS = "В этом разделе пока нет записей. Выбери дело в приложении — я напомню о нём здесь."
NO_CONTACT = "Эта запись недоступна для переписки. Открой /messages и выбери смену."
NO_COORDINATOR = (
    "Координатор этой смены ещё не подключил бота. "
    "Попробуй позже; инструкции и адрес доступны в /my."
)
CONSENT_REQUIRED = "Сначала пройди знакомство с приложением и дай согласие на обработку данных."

async def remember_chat(session: AsyncSession, user: User, chat_id: int) -> None:
    await session.execute(
        pg_insert(MaxChat)
        .values(user_id=user.id, chat_id=chat_id)
        .on_conflict_do_update(index_elements=[MaxChat.user_id], set_={"chat_id": chat_id})
    )

async def respond(command: str, *, max_user_id: int, first_name: str | None, chat_id: int) -> None:
    replies: list[tuple[str, OutgoingAttachment]] = []
    async with db.transaction() as session:
        user = await upsert_user(session, max_user_id, first_name)
        await session.flush()
        await remember_chat(session, user, chat_id)
        if not command.startswith(keyboards.CONTACT_PREFIX):
            await select_conversation(session, user.id, None)
        if command == "cancel":
            await select_conversation(session, user.id, None)
            replies.append(
                ("Диалог завершён. Новое сообщение можно начать через /messages.", keyboards.menu())
            )
        elif command.split(":", 1)[0] in ("my", "messages"):
            replies = await _bookings(session, user, command)
        elif command.startswith(keyboards.BOOKING_PREFIX):
            replies = [await _booking_detail(session, user, command)]
        elif command == "back":
            replies = [("Выбери раздел:", keyboards.menu())]
        elif command.startswith(keyboards.CONTACT_PREFIX):
            replies.append(
                await _contact(session, user, command.removeprefix(keyboards.CONTACT_PREFIX))
            )
        else:
            replies.append((HELP, keyboards.menu()))
    for text, attachment in replies:
        await notify.send_to_chat(chat_id, text, attachments=[attachment])

PAGE_SIZE = 5
STATUS_LABEL = {
    BookingStatus.GOING: "Записан",
    BookingStatus.CHECKED_IN: "На месте",
    BookingStatus.MANUAL: "Участие отмечено",
    BookingStatus.DONE: "Завершено",
    BookingStatus.NO_SHOW: "Неявка",
    BookingStatus.CANCELLED: "Запись отменена",
}

def _list_context(command: str) -> tuple[str, str, int]:
    parts = command.split(":")
    kind = "messages" if parts[0] == "messages" else "my"
    section = "history" if len(parts) > 1 and parts[1] == "history" else "upcoming"
    page = min(int(parts[2]), 10000) if len(parts) > 2 and parts[2].isdigit() else 0
    return kind, section, page

async def _bookings(
    session: AsyncSession, user: User, command: str
) -> list[tuple[str, OutgoingAttachment]]:
    if user.consent_at is None:
        return [(CONSENT_REQUIRED, keyboards.menu())]
    kind, section, page = _list_context(command)
    upcoming = and_(
        Shift.ends_at > current_time(),
        Shift.status == ShiftStatus.OPEN,
        Booking.status.in_((BookingStatus.GOING, BookingStatus.CHECKED_IN, BookingStatus.MANUAL)),
    )
    query = (
        select(Booking, Shift)
        .join(Shift, Shift.id == Booking.shift_id)
        .where(Booking.user_id == user.id)
    )
    query = query.where(upcoming if section == "upcoming" else not_(upcoming))
    if kind == "messages":
        query = query.where(
            Booking.status != BookingStatus.CANCELLED, Shift.status != ShiftStatus.CANCELLED
        )
    order = Shift.starts_at if section == "upcoming" else Shift.starts_at.desc()
    rows = (
        await session.execute(
            query.order_by(order, Booking.id).offset(page * PAGE_SIZE).limit(PAGE_SIZE + 1)
        )
    ).all()
    title = "Написать координатору" if kind == "messages" else "Мои записи"
    lines = [f"{title} · {'История' if section == 'history' else 'Предстоящие'}"]
    buttons = []
    for number, (booking, shift) in enumerate(rows[:PAGE_SIZE], page * PAGE_SIZE + 1):
        status = (
            "Событие отменено"
            if shift.status == ShiftStatus.CANCELLED
            else STATUS_LABEL[booking.status]
        )
        lines.append(f"{number}. {shift.title} · {notify.fmt_when(shift.starts_at)} · {status}")
        action = (
            f"{keyboards.CONTACT_PREFIX}{booking.id}"
            if kind == "messages"
            else f"{keyboards.BOOKING_PREFIX}{booking.id}:{section}:{page}"
        )
        buttons.append([CallbackButton(text=f"{number}. {shift.title}"[:80], payload=action)])
    if not rows:
        lines = [NO_BOOKINGS]
    pages = []
    if page:
        pages.append(
            CallbackButton(text="‹ Предыдущие", payload=f"menu:{kind}:{section}:{page - 1}")
        )
    if len(rows) > PAGE_SIZE:
        pages.append(
            CallbackButton(text="Следующие ›", payload=f"menu:{kind}:{section}:{page + 1}")
        )
    if pages:
        buttons.append(pages)
    other = "upcoming" if section == "history" else "history"
    buttons.append(
        [
            CallbackButton(
                text="Предстоящие" if other == "upcoming" else "История",
                payload=f"menu:{kind}:{other}:0",
            ),
            keyboards.back_menu(),
        ]
    )
    return [("\n\n".join(lines), keyboards.keyboard(buttons))]

async def _booking_detail(
    session: AsyncSession, user: User, command: str
) -> tuple[str, OutgoingAttachment]:
    if user.consent_at is None:
        return CONSENT_REQUIRED, keyboards.menu()
    parts = command.split(":")
    try:
        booking = await session.get(Booking, uuid.UUID(parts[1]))
    except (ValueError, IndexError):
        return NO_CONTACT, keyboards.menu()
    if booking is None or booking.user_id != user.id:
        return NO_CONTACT, keyboards.menu()
    shift = await session.get(Shift, booking.shift_id)
    if shift is None:
        return NO_CONTACT, keyboards.menu()
    _, section, page = _list_context("my:" + ":".join(parts[2:]))
    text = (
        f"{shift.title} · {notify.fmt_when(shift.starts_at)}\n{STATUS_LABEL[booking.status]}\n"
        f"Адрес: {shift.address}\n{shift.address_note or ''}\n"
        f"Инструкция: {shift.instructions or 'Особых условий нет.'}"
    )
    contact = booking.status != BookingStatus.CANCELLED and shift.status != ShiftStatus.CANCELLED
    return text, keyboards.booking_actions(
        str(booking.id), str(shift.id), f"my:{section}:{page}", contact=contact
    )

async def select_conversation(
    session: AsyncSession, user_id: uuid.UUID, relay_id: uuid.UUID | None
) -> None:
    values = {"relay_id": relay_id, "expires_at": current_time() + timedelta(hours=24)}
    await session.execute(
        pg_insert(BotConversation)
        .values(user_id=user_id, **values)
        .on_conflict_do_update(index_elements=[BotConversation.user_id], set_=values)
    )

async def _contact(
    session: AsyncSession, user: User, raw_booking_id: str
) -> tuple[str, OutgoingAttachment]:
    if user.consent_at is None:
        return CONSENT_REQUIRED, keyboards.menu()
    try:
        booking_id = uuid.UUID(raw_booking_id)
    except ValueError:
        return NO_CONTACT, keyboards.menu()
    booking = await session.get(Booking, booking_id)
    if booking is None or booking.user_id != user.id or booking.status == BookingStatus.CANCELLED:
        return NO_CONTACT, keyboards.menu()
    shift = await session.get(Shift, booking.shift_id)
    if shift is None or shift.status == ShiftStatus.CANCELLED:
        return NO_CONTACT, keyboards.menu()
    coordinator = await session.scalar(
        select(User)
        .join(OrgMember, OrgMember.user_id == User.id)
        .join(Org, Org.id == OrgMember.org_id)
        .join(MaxChat, MaxChat.user_id == User.id)
        .where(
            OrgMember.org_id == shift.org_id,
            OrgMember.revoked_at.is_(None),
            Org.status == OrgStatus.VERIFIED,
            User.id != user.id,
        )
        .order_by((User.id == shift.created_by).desc(), OrgMember.created_at, User.id)
        .limit(1)
    )
    if coordinator is None:
        return NO_COORDINATOR, keyboards.menu()
    existing = await session.scalar(
        select(MessageRelay)
        .join(Message, Message.id == MessageRelay.message_id)
        .where(
            Message.shift_id == shift.id,
            MessageRelay.participant_id == user.id,
            MessageRelay.coordinator_id == coordinator.id,
            MessageRelay.direction == RelayDirection.TO_PARTICIPANT,
            MessageRelay.created_at >= current_time() - timedelta(hours=24),
        )
        .order_by(MessageRelay.created_at.desc())
        .limit(1)
    )
    if existing is None:
        thread = Message(
            shift_id=shift.id,
            audience=MessageAudience.ALL,
            text="Личный диалог по записи",
            created_by=coordinator.id,
        )
        session.add(thread)
        await session.flush()
        existing = MessageRelay(
            message_id=thread.id,
            participant_id=user.id,
            coordinator_id=coordinator.id,
            direction=RelayDirection.TO_PARTICIPANT,
        )
        session.add(existing)
        await session.flush()
    await select_conversation(session, user.id, existing.id)
    return (
        f"Диалог со сменой «{shift.title}». Напиши вопрос одним текстовым сообщением — "
        "я передам его координатору, а ответ пришлю сюда. "
        "Следующие сообщения в течение суток идут этой смене. /cancel — завершить.",
        keyboards.end_conversation(),
    )
