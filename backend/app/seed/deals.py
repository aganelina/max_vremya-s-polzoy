from datetime import datetime, time, timedelta

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.enums import BookingStatus, Category, ShiftPlace, ShiftStatus, TransferStatus
from app.db.models import (
    Booking,
    Company,
    CompanyMember,
    FreeWindow,
    FriendInvite,
    SeatTransfer,
    Shift,
    User,
)
from app.domain.checkin_code import new_secret
from app.seed.guard import has_real_bookings
from app.seed.ids import DEMO_MAX_USER_ID, demo_id

log = structlog.get_logger("seed")

COMPANY_TOKEN = "demo_company_c_demo_01"  # noqa: S105 — демо-ссылка
TRANSFER_TOKEN = "demo_transfer_d_books0"  # noqa: S105
INVITE_TOKEN = "demo_invite_d_books_01"  # noqa: S105
INSTRUCTIONS = "Подойди к синему шатру у входа, спроси Гульнару"

PEOPLE = [
    ("u-artur", "Артур", 900101),
    ("u-kamila", "Камила", 900102),
    ("u-ruslan", "Руслан", 900103),
    ("u-timur", "Тимур", 900105),
    ("u-sofya", "Софья", 900202),
    ("u-marat", "Марат", 900203),
    ("u-gulnara", "Гульнара", 900206),
    ("u-dima", "Дима", 900301),
    ("u-leila", "Лейла", 900302),
    ("u-elza", "Эльза", 900303),
    ("u-vadim", "Вадим", 900304),
    ("u-niyaz", "Нияз", 900305),
    ("u-oleg", "Олег", 900306),
    ("u-farid", "Фарид", 900307),
    ("u-shamil", "Шамиль", 900308),
]

DEALS: list[
    tuple[str, str, str, Category, int, str, int, str, str | None, int, list[str], str, str | None]
] = [
    (
        "d-books",
        "Разбор книг для сельских библиотек (демо)",
        "o-books",
        Category.BOOKS,
        2,
        "18:05",
        90,
        "ул. Баумана, 19",
        "вход со двора",
        8,
        ["u-dima", "u-marat", "u-kamila", "u-timur", "u-sofya"],
        "Разобрать пожертвованные книги по возрасту и темам, упаковать в коробки для трёх "
        "сельских библиотек. Всё покажут на месте.",
        "3 коробки книг уедут в сёла области",
    ),
    (
        "d-sort",
        "Сортировка вещей в пункте помощи (демо)",
        "o-aid",
        Category.THINGS,
        0,
        "17:45",
        60,
        "ул. Карла Маркса, 40",
        None,
        4,
        ["u-ruslan"],
        "Разложить принесённые вещи по размерам и сезонам, собрать наборы для семей. "
        "Перчатки выдадут.",
        "вещи дойдут до 20 семей на этой неделе",
    ),
    (
        "d-read",
        "Чтение вслух в доме ветеранов (демо)",
        "o-silver",
        Category.PEOPLE,
        0,
        "18:10",
        40,
        "ул. Бутлерова, 31",
        None,
        3,
        ["u-elza"],
        "Почитать вслух газету или рассказ, поговорить. Книги есть на месте.",
        None,
    ),
    (
        "d-food",
        "Упаковка продуктовых наборов (демо)",
        "o-food",
        Category.THINGS,
        0,
        "18:30",
        60,
        "ул. Декабристов, 8",
        None,
        10,
        ["u-artur", "u-vadim", "u-gulnara"],
        "Собрать продуктовые наборы по списку и подписать коробки.",
        None,
    ),
    (
        "d-dogs",
        "Выгул собак из приюта (демо)",
        "o-paw",
        Category.ANIMALS,
        0,
        "18:20",
        60,
        "ул. Сибирский тракт, 34",
        None,
        6,
        ["u-niyaz", "u-oleg"],
        "Погулять с собаками в парке рядом с приютом. Поводки и пакеты выдадут.",
        None,
    ),
    (
        "d-blood",
        "Помощь на донорской акции (демо)",
        "o-blood",
        Category.PEOPLE,
        0,
        "18:45",
        30,
        "ул. Пушкина, 3",
        None,
        4,
        [],
        "Встречать доноров, помогать заполнить анкету, раздавать чай.",
        None,
    ),
    (
        "d-park",
        "Уборка сквера у озера Кабан (демо)",
        "o-green",
        Category.ECOLOGY,
        1,
        "17:00",
        90,
        "наб. озера Кабан",
        None,
        5,
        ["u-leila", "u-farid", "u-shamil"],
        "Собрать мусор вдоль набережной, рассортировать. Инвентарь выдадут.",
        None,
    ),
]

WINDOWS = [
    ("w1", 2, "11:10", "13:10", "после «История»"),
    ("w2", 2, "14:40", "17:00", "после «Обед с группой»"),
    ("w3", 4, "15:10", "17:00", "свободно до конца дня"),
]

def _at(now: datetime, days: int, hm: str) -> datetime:
    tz = get_settings().tz
    hh, mm = map(int, hm.split(":"))
    day = now.astimezone(tz).date() + timedelta(days=days)
    return datetime.combine(day, time(hh, mm), tzinfo=tz)

def _weekday(now: datetime, dow: int, hm: str) -> datetime:
    today = now.astimezone(get_settings().tz).isoweekday()
    return _at(now, (dow - today) % 7, hm)

async def _person(
    session: AsyncSession, now: datetime, key: str, name: str, max_user_id: int
) -> User:
    user = await session.get(User, demo_id(key))
    if user is None:
        user = await session.scalar(select(User).where(User.max_user_id == max_user_id))
    if user is None:
        user = User(id=demo_id(key), max_user_id=max_user_id, first_name=name)
        user.consent_at = _at(now, -20, "12:00")
        user.onboarded_at = user.consent_at
        user.university_id = "kfu"
        user.district_id = "vakh"
        session.add(user)
        await session.flush()
    return user

async def _booking(
    session: AsyncSession, key: str, shift: Shift, user: User, now: datetime, order: int = 0
) -> Booking:
    existing = await session.scalar(
        select(Booking).where(
            Booking.shift_id == shift.id,
            Booking.user_id == user.id,
            Booking.status != BookingStatus.CANCELLED,
        )
    )
    if existing is not None:
        return existing
    booking = await session.merge(
        Booking(
            id=demo_id(key),
            shift_id=shift.id,
            user_id=user.id,
            status=BookingStatus.GOING,
            checked_in_at=None,
            created_at=now - timedelta(days=1) + timedelta(minutes=order),
        )
    )
    await session.flush()
    return booking

async def seed_deals(session: AsyncSession, now: datetime) -> None:
    alina = await session.scalar(select(User).where(User.max_user_id == DEMO_MAX_USER_ID))
    assert alina is not None, "seed_demo_user должен идти раньше"
    people = {key: await _person(session, now, key, name, mid) for key, name, mid in PEOPLE}

    shifts: dict[str, Shift] = {}
    for (
        key,
        title,
        org,
        category,
        day,
        start,
        minutes,
        address,
        note,
        capacity,
        going,
        description,
        impact,
    ) in DEALS:
        starts_at = _at(now, day, start)
        shift = await session.get(Shift, demo_id(key))
        if shift is not None and await has_real_bookings(session, shift.id):
            log.info("seed_shift_skipped", shift=key, reason="real_bookings")
            shifts[key] = shift
            continue
        if shift is None:
            shift = Shift(id=demo_id(key), checkin_secret=new_secret())
            session.add(shift)
        shift.org_id = demo_id(org)
        shift.title = title
        shift.description = description
        shift.category = category
        shift.starts_at = starts_at
        shift.ends_at = starts_at + timedelta(minutes=minutes)
        shift.capacity = capacity
        shift.place = ShiftPlace.ORG
        shift.address = address
        shift.address_note = note
        shift.instructions = INSTRUCTIONS
        shift.impact = impact
        shift.status = ShiftStatus.OPEN
        await session.flush()
        shifts[key] = shift
        for order, person in enumerate(going):
            await _booking(session, f"b-{key}-{person}", shift, people[person], now, order)

    await _booking(session, "b-books", shifts["d-books"], alina, now, 10)

    timur_booking = await _booking(
        session, "b-d-books-u-timur", shifts["d-books"], people["u-timur"], now
    )
    await session.merge(
        SeatTransfer(
            id=demo_id("t-books"),
            booking_id=timur_booking.id,
            token=TRANSFER_TOKEN,
            status=TransferStatus.OPEN,
            claimed_by=None,
            expires_at=shifts["d-books"].starts_at,
        )
    )
    await session.merge(
        FriendInvite(
            id=demo_id("fr-books"),
            token=INVITE_TOKEN,
            shift_id=shifts["d-books"].id,
            inviter_id=people["u-dima"].id,
        )
    )

    company = await session.merge(
        Company(
            id=demo_id("c-demo"),
            owner_id=alina.id,
            token=COMPANY_TOKEN,
            date=now.astimezone(get_settings().tz).date(),
            picked_shift_id=shifts["d-books"].id,
        )
    )
    await session.flush()
    await session.execute(delete(CompanyMember).where(CompanyMember.company_id == company.id))
    members = [
        (alina, "17:00", "19:40", 0),
        (people["u-dima"], "17:30", "21:00", 1),
        (people["u-leila"], None, None, 2),
    ]
    for user, frm, to, order in members:
        session.add(
            CompanyMember(
                company_id=company.id,
                user_id=user.id,
                window_from=_at(now, 0, frm) if frm else None,
                window_to=_at(now, 0, to) if to else None,
                reminded_at=None,
                joined_at=now - timedelta(hours=3 - order),
            )
        )

    await session.execute(delete(FreeWindow).where(FreeWindow.user_id == alina.id))
    for key, dow, frm, to, after in WINDOWS:
        session.add(
            FreeWindow(
                id=demo_id(key),
                user_id=alina.id,
                starts_at=_weekday(now, dow, frm),
                ends_at=_weekday(now, dow, to),
                after_label=after,
                place_label="КФУ, главный",
            )
        )
    await session.flush()
