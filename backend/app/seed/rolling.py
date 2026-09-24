from collections.abc import Iterator
from datetime import datetime, time, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.enums import BookingStatus, Category, ShiftPlace, ShiftStatus
from app.db.models import Booking, Shift, User
from app.domain.checkin_code import new_secret
from app.seed.guard import has_real_bookings
from app.seed.ids import demo_id

log = structlog.get_logger("seed")

LAST_START = time(21, 30)
CALENDAR_DAYS = 42

Start = int | tuple[int, str]
ROLLING: list[tuple[str, str, str, Category, Start, int, ShiftPlace, str, int, list[str], str]] = [
    (
        "r-blood",
        "Встречать гостей донорской акции (демо)",
        "o-blood",
        Category.PEOPLE,
        15,
        60,
        ShiftPlace.ORG,
        "ул. Пушкина, 3",
        6,
        ["u-timur", "u-sofya"],
        "Встречать доноров у входа, помогать с анкетой и раздавать чай после сдачи крови.",
    ),
    (
        "r-letters",
        "Подписать открытки для дома престарелых (демо)",
        "o-silver",
        Category.PEOPLE,
        25,
        40,
        ShiftPlace.ORG,
        "ул. Бутлерова, 31",
        6,
        ["u-elza"],
        "Подписать открытки к Дню пожилых людей: пара тёплых строк от себя. Открытки на месте.",
    ),
    (
        "r-shelf",
        "Собрать книжную полку для детской библиотеки (демо)",
        "o-home",
        Category.BOOKS,
        30,
        45,
        ShiftPlace.ORG,
        "ул. Островского, 57",
        5,
        ["u-dima", "u-kamila"],
        "Расставить подаренные книги по возрастам и подписать разделители.",
    ),
    (
        "r-map",
        "Отметить на карте контейнеры для раздельного сбора (демо)",
        "o-green",
        Category.ECOLOGY,
        35,
        30,
        ShiftPlace.ONLINE,
        "онлайн",
        20,
        ["u-farid"],
        "Пройтись по фото из чата и отметить на карте, где стоят контейнеры для пластика и стекла.",
    ),
    (
        "r-aid",
        "Разгрузить машину с зимними вещами (демо)",
        "o-aid",
        Category.THINGS,
        40,
        60,
        ShiftPlace.ORG,
        "ул. Карла Маркса, 40",
        4,
        ["u-ruslan"],
        "Перенести мешки с вещами из машины на склад пункта. Тяжёлое носим вдвоём.",
    ),
    (
        "r-call",
        "Позвонить одинокому пожилому человеку (демо)",
        "o-home",
        Category.ONLINE,
        55,
        30,
        ShiftPlace.ONLINE,
        "онлайн",
        10,
        [],
        "Короткий разговор по телефону: спросить, как дела, и напомнить про визит врача.",
    ),
    (
        "r-cats",
        "Покормить и поиграть с котами в приюте (демо)",
        "o-paw",
        Category.ANIMALS,
        50,
        60,
        ShiftPlace.ORG,
        "ул. Сибирский тракт, 34",
        4,
        ["u-niyaz"],
        "Покормить котов, поменять лотки и поиграть с теми, кто скучает. Халат выдадут.",
    ),
    (
        "r-bags",
        "Разложить продукты по пакетам (демо)",
        "o-food",
        Category.THINGS,
        60,
        45,
        ShiftPlace.ORG,
        "ул. Декабристов, 8",
        8,
        ["u-artur", "u-vadim", "u-oleg"],
        "Разложить крупы, консервы и чай по пакетам для семей из списка фонда.",
    ),
    (
        "r-yard",
        "Убрать листья во дворе детского дома (демо)",
        "o-home",
        Category.ECOLOGY,
        (1, "17:50"),
        50,
        ShiftPlace.ORG,
        "ул. Островского, 57",
        10,
        ["u-leila", "u-shamil"],
        "Сгрести листья и вынести мешки. Грабли и перчатки выдадут.",
    ),
    (
        "r-sort2",
        "Принять и рассортировать зимние вещи (демо)",
        "o-aid",
        Category.THINGS,
        (1, "18:00"),
        60,
        ShiftPlace.ORG,
        "ул. Карла Маркса, 40",
        6,
        ["u-ruslan", "u-sofya"],
        "Принять пакеты от жителей, отобрать тёплые вещи и разложить по размерам.",
    ),
    (
        "r-homework",
        "Помочь с домашкой по математике (демо)",
        "o-home",
        Category.PEOPLE,
        (1, "18:10"),
        50,
        ShiftPlace.ORG,
        "ул. Островского, 57",
        3,
        ["u-marat"],
        "Позаниматься с ребятами 5–7 классов: дроби, уравнения, задачи на движение.",
    ),
    (
        "r-flyers",
        "Разнести листовки о дне донора по общежитиям (демо)",
        "o-blood",
        Category.PEOPLE,
        (1, "18:30"),
        45,
        ShiftPlace.ORG,
        "ул. Пушкина, 3",
        8,
        ["u-vadim"],
        "Забрать листовки в центре крови и разложить на стойках трёх общежитий рядом.",
    ),
    (
        "r-fair",
        "Помочь на благотворительной ярмарке (демо)",
        "o-silver",
        Category.PEOPLE,
        (-1, "11:20"),
        80,
        ShiftPlace.ORG,
        "ул. Бутлерова, 31",
        12,
        ["u-artur", "u-timur"],
        "Встречать гостей, помогать на кассе и с выпечкой. Вся выручка — в фонд.",
    ),
    (
        "r-cleanup",
        "Субботник на набережной Кабана (демо)",
        "o-green",
        Category.ECOLOGY,
        (-1, "11:30"),
        60,
        ShiftPlace.ORG,
        "наб. озера Кабан",
        15,
        ["u-leila", "u-farid"],
        "Собрать мусор вдоль набережной и рассортировать по мешкам. Инвентарь выдадут.",
    ),
    (
        "r-tales",
        "Почитать сказки малышам (демо)",
        "o-home",
        Category.BOOKS,
        (-1, "11:40"),
        50,
        ShiftPlace.ORG,
        "ул. Островского, 57",
        4,
        ["u-kamila"],
        "Почитать вслух детям 4–6 лет и поиграть по мотивам сказки. Книги на месте.",
    ),
    (
        "r-dogs-weekend",
        "Большая прогулка с собаками (демо)",
        "o-paw",
        Category.ANIMALS,
        (-1, "11:20"),
        90,
        ShiftPlace.ORG,
        "ул. Сибирский тракт, 34",
        8,
        ["u-niyaz", "u-oleg"],
        "Погулять с собаками в лесопарке: два круга по 40 минут. Поводки выдадут.",
    ),
]

def _start(now: datetime, when: Start) -> datetime | None:
    tz = get_settings().tz
    local = now.astimezone(tz)
    if isinstance(when, int):
        at = (local + timedelta(minutes=when)).replace(second=0, microsecond=0)
        at += timedelta(minutes=(-at.minute) % 5)
        if at.date() != local.date() or at.time() > LAST_START:
            return None
        return at
    days, hm = when
    if days < 0:
        days = (5 - local.weekday()) % 7
    hh, mm = map(int, hm.split(":"))
    return datetime.combine(local.date() + timedelta(days=days), time(hh, mm), tzinfo=tz)

def calendar_events(
    now: datetime,
) -> Iterator[tuple[str, str, str, Category, Start, int, ShiftPlace, str, int, list[str], str]]:
    from app.seed.deals import DEALS

    today = now.astimezone(get_settings().tz).date()
    for day in range(1, CALENDAR_DAYS + 1):
        for slot, hm in enumerate(("09:30", "12:15", "16:00", "18:15")):
            template = DEALS[(day + slot) % len(DEALS)]
            _, title, org, category, _, _, minutes, address, _, capacity, going, text, _ = template
            key = f"calendar-{today + timedelta(days=day)}-{slot}"
            yield (
                key,
                title,
                org,
                category,
                (day, hm),
                minutes,
                ShiftPlace.ORG,
                address,
                capacity,
                going[:2],
                text,
            )

async def seed_rolling(
    session: AsyncSession, now: datetime, *, calendar_only: bool = False
) -> None:
    for key, title, org, category, when, minutes, place, address, capacity, going, text in [
        *([] if calendar_only else ROLLING),
        *calendar_events(now),
    ]:
        shift = await session.get(Shift, demo_id(key))
        if shift is not None and key.startswith("calendar-"):
            continue
        if shift is not None and await has_real_bookings(session, shift.id):
            log.info("seed_rolling_skipped", shift=key, reason="real_bookings")
            continue
        starts_at = _start(now, when)
        if starts_at is None or starts_at <= now:
            if shift is not None:
                shift.status = ShiftStatus.CANCELLED
            continue
        if shift is None:
            shift = Shift(id=demo_id(key), checkin_secret=new_secret())
            session.add(shift)
        shift.org_id = demo_id(org)
        shift.title = title
        shift.description = text
        shift.category = category
        shift.starts_at = starts_at
        shift.ends_at = starts_at + timedelta(minutes=minutes)
        shift.capacity = capacity
        shift.place = place
        shift.address = address
        shift.address_note = None
        shift.instructions = "Координатор встретит у входа и всё покажет"
        shift.impact = None
        shift.status = ShiftStatus.OPEN
        await session.flush()
        for person in going:
            user = await session.get(User, demo_id(person))
            if user is None:
                continue
            exists = await session.scalar(
                select(Booking.id).where(
                    Booking.shift_id == shift.id,
                    Booking.user_id == user.id,
                    Booking.status != BookingStatus.CANCELLED,
                )
            )
            if exists is None:
                await session.merge(
                    Booking(
                        id=demo_id(f"b-{key}-{person}"),
                        shift_id=shift.id,
                        user_id=user.id,
                        status=BookingStatus.GOING,
                    )
                )
    await session.flush()
