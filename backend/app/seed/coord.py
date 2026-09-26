import os
from datetime import datetime, time, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.enums import (
    BookingStatus,
    Category,
    LedgerSource,
    MicroAnswerStatus,
    OrgRole,
    ShiftPlace,
    ShiftStatus,
)
from app.db.models import Booking, HourLedger, MicroAnswer, MicroTask, OrgMember, Shift, User
from app.domain.hours import shift_hours
from app.seed.guard import has_real_bookings
from app.seed.ids import demo_id

log = structlog.get_logger("seed")

PEOPLE = [
    ("u-alina-k", "Алина", 900201),
    ("u-timur", "Тимур", 900105),
    ("u-sofya", "Софья", 900202),
    ("u-marat", "Марат", 900203),
    ("u-ildar", "Ильдар", 900204),
    ("u-kamila", "Камила", 900102),
    ("u-ruslan", "Руслан", 900103),
    ("u-rinat", "Ринат", 900205),
    ("u-gulnara", "Гульнара", 900206),
]

ORG = "o-books"
COORDINATORS = ["u-gulnara", "u-rinat"]
INSTRUCTIONS = "Подойди к синему шатру у входа, спроси Гульнару"
ADDRESS = "ул. Пушкина, 12"

SHIFTS = [
    ("s-books", "Разбор книг для сельских библиотек (демо)", Category.BOOKS, 1, "18:00", 90, 8),
    ("s-kids", "Мастер-класс для детей (демо)", Category.BOOKS, 2, "18:30", 90, 6),
]

PARTICIPANTS = [
    ("u-alina-k", BookingStatus.CHECKED_IN, "17:56"),
    ("u-timur", BookingStatus.CHECKED_IN, "18:12"),
    ("u-sofya", BookingStatus.GOING, None),
    ("u-marat", BookingStatus.GOING, None),
    ("u-ildar", BookingStatus.NO_SHOW, None),
]

REVIEWS = [
    (
        "a",
        "u-kamila",
        20,
        "Вопросы для интервью с выпускниками детского дома",
        "Предложи 5–7 вопросов: что было сложнее всего, кто помог, что бы они посоветовали.",
        "1. Что оказалось самым неожиданным в первый месяц? 2. Кто помог, когда было трудно? "
        "3. Как ты искал жильё? 4. Что бы ты сказал себе в день выпуска? "
        "5. Чему стоит учить в детском доме уже сейчас?",
    ),
    (
        "b",
        "u-ruslan",
        20,
        "Напиши письмо пожилому человеку",
        "Короткое тёплое письмо: пара слов о себе и вопрос, на который приятно ответить.",
        "Здравствуйте! Меня зовут Руслан, я учусь на физфаке и люблю ходить пешком по старой "
        "Казани. А какая улица в городе была вашей любимой, когда вам было двадцать?",
    ),
    (
        "c",
        "u-alina-k",
        15,
        "Придумай подписи к фото из приюта",
        "Две-три строки к каждому фото: характер и чем зверь порадует нового хозяина.",
        "Бублик: спит 20 часов в сутки, оставшиеся 4 ждёт тебя. "
        "Мира: осторожная, но если подружится — навсегда.",
    ),
]

HISTORY = [
    (
        "ms-books-1",
        "o-books",
        "Сортировка книжных пожертвований (демо)",
        6,
        120,
        [("u-alina-k", True), ("u-timur", True), ("u-sofya", True), ("u-ildar", False)],
    ),
    (
        "ms-books-2",
        "o-books",
        "Книжный обмен у корпуса (демо)",
        13,
        90,
        [("u-timur", True), ("u-marat", True), ("u-kamila", True), ("u-ruslan", False)],
    ),
    (
        "ms-books-3",
        "o-books",
        "Разбор книг для сельских библиотек (демо)",
        20,
        90,
        [("u-alina-k", True), ("u-sofya", True), ("u-ruslan", True)],
    ),
    (
        "ms-green-1",
        "o-green",
        "Уборка сквера у озера Кабан (демо)",
        9,
        90,
        [("u-kamila", True), ("u-marat", True), ("u-ildar", True), ("u-ruslan", False)],
    ),
]

def _at(now: datetime, days: int, hm: str) -> datetime:
    tz = get_settings().tz
    day = now.astimezone(tz).date() + timedelta(days=days)
    return datetime.combine(day, time.fromisoformat(hm), tzinfo=tz)

async def _person(session: AsyncSession, now: datetime, key: str, name: str, max_id: int) -> User:
    user = await session.get(User, demo_id(key))
    if user is None:
        user = await session.scalar(select(User).where(User.max_user_id == max_id))
    if user is None:
        user = User(id=demo_id(key), max_user_id=max_id)
        session.add(user)
    user.first_name = name
    user.consent_at = user.consent_at or _at(now, -20, "12:00")
    user.onboarded_at = user.onboarded_at or user.consent_at
    user.university_id = user.university_id or "kfu"
    user.district_id = user.district_id or "vakh"
    await session.flush()
    return user

async def _shift(
    session: AsyncSession,
    key: str,
    org: str,
    title: str,
    category: Category,
    starts_at: datetime,
    minutes: int,
    capacity: int,
    status: ShiftStatus,
) -> Shift:
    shift = await session.get(Shift, demo_id(key))
    if shift is not None and await has_real_bookings(session, shift.id):
        log.info("seed_shift_skipped", shift=key, reason="real_bookings")
        return shift
    if shift is None:
        shift = Shift(id=demo_id(key), org_id=demo_id(org), checkin_secret=os.urandom(20))
        session.add(shift)
    shift.title = title
    shift.category = category
    shift.starts_at = starts_at
    shift.ends_at = starts_at + timedelta(minutes=minutes)
    shift.capacity = capacity
    shift.place = ShiftPlace.ORG
    shift.address = ADDRESS
    shift.instructions = INSTRUCTIONS
    shift.status = status
    await session.flush()
    return shift

async def _booking(
    session: AsyncSession,
    key: str,
    shift: Shift,
    user: User,
    status: BookingStatus,
    checked_in_at: datetime | None,
    created_at: datetime,
) -> Booking:
    booking = await session.merge(
        Booking(
            id=demo_id(key),
            shift_id=shift.id,
            user_id=user.id,
            status=status,
            checked_in_at=checked_in_at,
            cancelled_at=None,
            created_at=created_at,
        )
    )
    await session.flush()
    return booking

async def seed_coord(session: AsyncSession, now: datetime) -> None:
    people = {key: await _person(session, now, key, name, mid) for key, name, mid in PEOPLE}
    org_id = demo_id(ORG)

    for key in COORDINATORS:
        await session.execute(
            pg_insert(OrgMember)
            .values(org_id=org_id, user_id=people[key].id, role=OrgRole.COORDINATOR)
            .on_conflict_do_update(
                index_elements=[OrgMember.org_id, OrgMember.user_id],
                set_={"role": OrgRole.COORDINATOR, "revoked_at": None},
            )
        )

    shifts = {}
    for key, title, category, day, start, minutes, capacity in SHIFTS:
        shifts[key] = await _shift(
            session,
            key,
            ORG,
            title,
            category,
            _at(now, day, start),
            minutes,
            capacity,
            ShiftStatus.OPEN,
        )
    books = shifts["s-books"]
    for index, (key, status, hm) in enumerate(PARTICIPANTS, start=1):
        await _booking(
            session,
            f"cb-p{index}",
            books,
            people[key],
            status,
            _at(now, 1, hm) if hm else None,
            now - timedelta(days=2, minutes=-index),
        )

    answer_ids = [demo_id(f"rv-{key}-answer") for key, *_ in REVIEWS]
    await session.execute(
        delete(HourLedger).where(
            HourLedger.source == LedgerSource.MICRO, HourLedger.ref_id.in_(answer_ids)
        )
    )
    for index, (key, author, minutes, title, text, answer) in enumerate(REVIEWS):
        await session.merge(
            MicroTask(
                id=demo_id(f"rv-{key}-task"),
                org_id=org_id,
                title=title,
                text=text,
                minutes=minutes,
                answers_needed=5,
                active=True,
                created_at=now - timedelta(days=3),
            )
        )
        await session.flush()
        await session.merge(
            MicroAnswer(
                id=demo_id(f"rv-{key}-answer"),
                task_id=demo_id(f"rv-{key}-task"),
                user_id=people[author].id,
                status=MicroAnswerStatus.SENT,
                answer=answer,
                deadline=None,
                review_note=None,
                reviewed_by=None,
                reviewed_at=None,
                created_at=now - timedelta(hours=5 - index),
            )
        )
    await session.flush()

    booking_ids = [
        demo_id(f"{key}-{person}") for key, *_, visits in HISTORY for person, _ in visits
    ]
    await session.execute(
        delete(HourLedger).where(
            HourLedger.source == LedgerSource.SHIFT, HourLedger.ref_id.in_(booking_ids)
        )
    )
    for key, org, title, days_ago, minutes, visits in HISTORY:
        shift = await _shift(
            session,
            key,
            org,
            title,
            Category.BOOKS if org == ORG else Category.ECOLOGY,
            _at(now, -days_ago, "17:00"),
            minutes,
            8,
            ShiftStatus.FINISHED,
        )
        hours: Decimal = shift_hours(shift.starts_at, shift.ends_at)
        for person, came in visits:
            booking = await _booking(
                session,
                f"{key}-{person}",
                shift,
                people[person],
                BookingStatus.DONE if came else BookingStatus.NO_SHOW,
                shift.starts_at - timedelta(minutes=5) if came else None,
                shift.starts_at - timedelta(days=2),
            )
            if came:
                session.add(
                    HourLedger(
                        user_id=people[person].id,
                        source=LedgerSource.SHIFT,
                        ref_id=booking.id,
                        hours=hours,
                        org_id=shift.org_id,
                        accepted_at=shift.ends_at,
                    )
                )
    await session.flush()
