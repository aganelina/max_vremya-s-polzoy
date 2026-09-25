import os
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.enums import (
    BookingStatus,
    Category,
    HelpStatus,
    LedgerSource,
    MentorRequestStatus,
    ShiftStatus,
)
from app.db.models import (
    Booking,
    HelpRequest,
    HelpResponse,
    HourLedger,
    MentorRequest,
    MentorSettings,
    MicroAnswer,
    MicroTask,
    Shift,
    User,
)
from app.domain.bank import balance
from app.seed.ids import DEMO_MAX_USER_ID, demo_id

PEOPLE = [
    ("u-artur", "Артур", 900101),
    ("u-kamila", "Камила", 900102),
    ("u-ruslan", "Руслан", 900103),
    ("u-dinara", "Динара", 900104),
    ("u-timur", "Тимур", 900105),
]

MICRO = [
    (
        "m1",
        "o-paw",
        "Проверь текст объявления о пристройстве собак",
        15,
        "Прочитай объявление и предложи, как сделать его понятнее и теплее. "
        "Можно поправить заголовок или первые две строки.",
    ),
    (
        "m2",
        "o-books",
        "Подбери 5 книг для подростковой полки",
        10,
        "Напиши пять книг, которые ты бы сам посоветовал читателю 13–15 лет, "
        "и одну фразу, почему каждую.",
    ),
    (
        "m3",
        "o-silver",
        "Напиши письмо пожилому человеку",
        20,
        "Короткое тёплое письмо: пара слов о себе и вопрос, на который человеку будет "
        "приятно ответить. Координатор распечатает и передаст.",
    ),
    (
        "m4",
        "o-home",
        "Вопросы для интервью с выпускниками детского дома о первом годе самостоятельной жизни",
        20,
        "Предложи 5–7 вопросов: что было сложнее всего, кто помог, что бы они посоветовали "
        "тем, кто выпускается сейчас.",
    ),
]

BANK = [
    (
        "o1",
        "u-dinara",
        "Подменить на стойке регистрации конференции",
        "1",
        "четверг, 12:00",
        HelpStatus.OPEN,
        None,
    ),
    (
        "o2",
        "u-timur",
        "Помочь собрать шкаф в общежитии",
        "2",
        "суббота, 11:00",
        HelpStatus.OPEN,
        None,
    ),
    (
        "my1",
        "u-alina",
        "Помочь донести коробки на 4 этаж",
        "1",
        "среда, 18:00",
        HelpStatus.MATCHED,
        "u-artur",
    ),
]

ALINA_BALANCE = Decimal("2.5")

def _at(now: datetime, days: int, hh: int, mm: int) -> datetime:
    tz = get_settings().tz
    day = now.astimezone(tz).date() + timedelta(days=days)
    return datetime.combine(day, time(hh, mm), tzinfo=tz)

async def _person(
    session: AsyncSession, now: datetime, key: str, name: str, max_user_id: int
) -> User:
    user = await session.get(User, demo_id(key))
    if user is None:
        user = await session.scalar(select(User).where(User.max_user_id == max_user_id))
    if user is None:
        user = User(id=demo_id(key), max_user_id=max_user_id)
        session.add(user)
    user.first_name = name
    user.consent_at = user.consent_at or _at(now, -20, 12, 0)
    user.onboarded_at = user.onboarded_at or user.consent_at
    user.university_id = user.university_id or "kfu"
    user.district_id = "vakh"
    await session.flush()
    return user

async def _alina(session: AsyncSession) -> User:
    user = await session.scalar(select(User).where(User.max_user_id == DEMO_MAX_USER_ID))
    assert user is not None, "seed_demo_user должен идти раньше"
    return user

async def _shift(
    session: AsyncSession,
    key: str,
    *,
    org: str,
    title: str,
    category: Category,
    starts_at: datetime,
    minutes: int,
    capacity: int,
    address: str,
    description: str,
) -> Shift:
    shift = await session.get(Shift, demo_id(key))
    if shift is None:
        shift = Shift(
            id=demo_id(key),
            org_id=demo_id(org),
            title=title,
            category=category,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=minutes),
            capacity=capacity,
            address=address,
            description=description,
            status=ShiftStatus.OPEN,
            checkin_secret=os.urandom(20),
        )
        session.add(shift)
        await session.flush()
    return shift

async def seed_engagement(session: AsyncSession, now: datetime) -> None:
    alina = await _alina(session)
    people = {key: await _person(session, now, key, name, mid) for key, name, mid in PEOPLE}
    people["u-alina"] = alina

    for index, (key, org, title, minutes, text) in enumerate(MICRO):
        await session.merge(
            MicroTask(
                id=demo_id(key),
                org_id=demo_id(org),
                title=title,
                text=text,
                minutes=minutes,
                answers_needed=10,
                deadline_at=None,
                active=True,
                created_at=now - timedelta(days=7, minutes=-index),
            )
        )
    await session.flush()
    await session.execute(
        delete(MicroAnswer).where(
            MicroAnswer.user_id == alina.id,
            MicroAnswer.task_id.in_([demo_id(m[0]) for m in MICRO]),
        )
    )

    for index, (key, author, text, hours, when, status, helper) in enumerate(BANK):
        request_id = demo_id(f"bank-{key}")
        await session.execute(delete(HelpResponse).where(HelpResponse.request_id == request_id))
        await session.merge(
            HelpRequest(
                id=request_id,
                author_id=people[author].id,
                text=text,
                hours=Decimal(hours),
                when_label=when,
                district_id="vakh",
                status=status,
                helper_id=people[helper].id if helper else None,
                created_at=now - timedelta(hours=index + 1),
            )
        )
        await session.flush()
        if helper:
            session.add(HelpResponse(request_id=request_id, user_id=people[helper].id))
    await session.flush()
    spend = await balance(session, alina.id, now) - ALINA_BALANCE
    if spend > 0:
        session.add(
            HourLedger(
                user_id=alina.id,
                source=LedgerSource.BANK_SPEND,
                hours=-spend,
                accepted_at=_at(now, -20, 18, 0),
            )
        )

    await session.merge(MentorSettings(user_id=alina.id, accepting=True))
    park = await _shift(
        session,
        "d-park",
        org="o-green",
        title="Уборка сквера у озера Кабан (демо)",
        category=Category.ECOLOGY,
        starts_at=_at(now, 1, 17, 0),
        minutes=90,
        capacity=5,
        address="наб. озера Кабан",
        description="Собрать мусор вдоль набережной, рассортировать. Инвентарь выдадут.",
    )
    flowers = await _shift(
        session,
        "d-flowers",
        org="o-green",
        title="Высадка цветов у корпуса (демо)",
        category=Category.ECOLOGY,
        starts_at=_at(now, 1, 10, 0),
        minutes=60,
        capacity=6,
        address="ул. Кремлёвская, 18",
        description="Высадить рассаду на клумбах у главного корпуса. Перчатки выдадут.",
    )
    for newbie, shift, request_key, request_status in (
        ("u-kamila", park, "mr1", MentorRequestStatus.OPEN),
        ("u-ruslan", flowers, "pr", MentorRequestStatus.ACCEPTED),
    ):
        await session.merge(
            Booking(
                id=demo_id(f"b-{newbie}-{request_key}"),
                shift_id=shift.id,
                user_id=people[newbie].id,
                status=BookingStatus.GOING,
            )
        )
        await session.merge(
            MentorRequest(
                id=demo_id(request_key),
                newbie_id=people[newbie].id,
                shift_id=shift.id,
                mentor_id=alina.id,
                status=request_status,
            )
        )
    await session.execute(
        delete(Booking).where(Booking.user_id == alina.id, Booking.shift_id == park.id)
    )
    await session.flush()
