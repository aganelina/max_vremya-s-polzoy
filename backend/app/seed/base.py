import os
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.enums import (
    BookingStatus,
    Category,
    LedgerSource,
    MicroAnswerStatus,
    NotifyMode,
    OrgRole,
    OrgStatus,
    ShiftStatus,
    Transport,
)
from app.db.models import (
    Booking,
    District,
    DistrictAdjacency,
    HourLedger,
    MicroAnswer,
    MicroTask,
    Org,
    OrgMember,
    Shift,
    University,
    User,
)
from app.seed.ids import DEMO_MAX_USER_ID, demo_id

UNIVERSITIES = [
    ("kfu", "КФУ", 55.7904, 49.1208),
    ("u1", "КНИТУ", 55.7960, 49.1410),
    ("u2", "КАИ", 55.7968, 49.1296),
    ("u3", "КГМУ", 55.7885, 49.1352),
    ("u4", "КГЭУ", 55.8216, 49.0918),
    ("u5", "КГАСУ", 55.7629, 49.1447),
    ("u6", "Другой", 55.7963, 49.1088),
]

DISTRICTS = [
    ("vakh", "Вахитовский", 55.7887, 49.1221),
    ("d1", "Советский", 55.7870, 49.2050),
    ("d2", "Приволжский", 55.7420, 49.1530),
    ("d3", "Ново-Савиновский", 55.8260, 49.1300),
    ("d4", "Московский", 55.8160, 49.0720),
    ("d5", "Кировский", 55.7990, 48.9750),
    ("d6", "Авиастроительный", 55.8600, 49.0850),
]

ADJACENCY = {
    "vakh": ["d1", "d2", "d3", "d4"],
    "d1": ["vakh", "d2", "d3"],
    "d2": ["vakh", "d1"],
    "d3": ["vakh", "d1", "d4", "d6"],
    "d4": ["vakh", "d3", "d5", "d6"],
    "d5": ["d4", "d6"],
    "d6": ["d3", "d4", "d5"],
}

ORGS = [
    ("o-books", "Книжный мост (демо)", "ул. Баумана, 19", "vakh", 55.7899, 49.1150),
    ("o-aid", "Пункт на Карла Маркса (демо)", "ул. Карла Маркса, 40", "vakh", 55.7930, 49.1350),
    ("o-silver", "Серебряный возраст (демо)", "ул. Бутлерова, 31", "vakh", 55.7880, 49.1320),
    ("o-food", "Фудбанк (демо)", "ул. Декабристов, 8", "d3", 55.8110, 49.1150),
    ("o-paw", "Приют «Лапа» (демо)", "ул. Сибирский тракт, 34", "d1", 55.8040, 49.1850),
    ("o-blood", "Центр крови (демо)", "ул. Пушкина, 3", "vakh", 55.7920, 49.1230),
    ("o-green", "Зелёная Казань (демо)", "наб. озера Кабан", "vakh", 55.7800, 49.1200),
    ("o-home", "Фонд «Дом без стен» (демо)", "ул. Островского, 57", "vakh", 55.7850, 49.1150),
    ("o-patrol", "Зелёный патруль (демо)", "парк Урицкого", "d3", 55.8230, 49.1030),
    ("o-clean", "Чистый город (демо)", "наб. озера Кабан", "vakh", 55.7800, 49.1200),
    ("o-warm", "Тёплые руки (демо)", "ул. Оренбургский тракт, 140", "d2", 55.7510, 49.2030),
]

HISTORY: list[tuple[str, int, str, str, bool]] = [
    ("Высадка деревьев в парке Урицкого (демо)", 8, "o-patrol", "1.5", False),
    ("Письмо пожилому человеку (демо)", 15, "o-silver", "0.5", True),
    ("Сортировка вещей в пункте помощи (демо)", 23, "o-aid", "2.5", False),
    ("Чтение вслух в доме ветеранов (демо)", 32, "o-silver", "1", False),
    ("Уборка берега озера Кабан (демо)", 43, "o-clean", "2", False),
    ("Выгул собак из приюта (демо)", 51, "o-paw", "1.5", False),
    ("Помощь на донорской акции (демо)", 65, "o-blood", "3", False),
    ("Расшифровка архивных писем (демо)", 73, "o-home", "0.5", True),
    ("Мастер-класс для детей в больнице (демо)", 86, "o-warm", "2", False),
]

_HISTORY_CATEGORY = {
    "o-patrol": Category.ECOLOGY,
    "o-clean": Category.ECOLOGY,
    "o-aid": Category.THINGS,
    "o-silver": Category.PEOPLE,
    "o-paw": Category.ANIMALS,
    "o-blood": Category.PEOPLE,
    "o-warm": Category.PEOPLE,
    "o-home": Category.ONLINE,
}

def _local_noon(now: datetime, days_ago: int) -> datetime:
    tz = get_settings().tz
    day = now.astimezone(tz).date() - timedelta(days=days_ago)
    return datetime.combine(day, time(12, 0), tzinfo=tz)

async def seed_dictionaries(session: AsyncSession, now: datetime) -> None:
    for position, (key, name, lat, lon) in enumerate(UNIVERSITIES):
        await session.merge(University(id=key, name=name, lat=lat, lon=lon, position=position))
    for position, (key, name, lat, lon) in enumerate(DISTRICTS):
        await session.merge(District(id=key, name=name, lat=lat, lon=lon, position=position))
    await session.flush()
    await session.execute(
        pg_insert(DistrictAdjacency)
        .values(
            [
                {"district_id": d, "neighbor_id": n}
                for d, neighbors in ADJACENCY.items()
                for n in neighbors
            ]
        )
        .on_conflict_do_nothing()
    )

async def seed_orgs(session: AsyncSession, now: datetime) -> None:
    for key, name, address, district, lat, lon in ORGS:
        await session.merge(
            Org(
                id=demo_id(key),
                name=name,
                contact_name="Гульнара",
                contact_phone="+7 900 000-00-00",
                address=address,
                district_id=district,
                lat=lat,
                lon=lon,
                status=OrgStatus.VERIFIED,
                verified_at=now - timedelta(days=120),
                sign_name="Г. Р. Сафина",
                sign_position="координатор",
            )
        )
    await session.flush()

async def _demo_user(session: AsyncSession) -> User | None:
    return await session.scalar(select(User).where(User.max_user_id == DEMO_MAX_USER_ID))

async def seed_demo_user(session: AsyncSession, now: datetime) -> None:
    user = await _demo_user(session)
    if user is None:
        user = User(id=demo_id("u-alina"), max_user_id=DEMO_MAX_USER_ID)
        session.add(user)
    user.first_name = "Алина"
    user.consent_at = _local_noon(now, 30)
    user.onboarded_at = user.consent_at
    user.university_id = "kfu"
    user.district_id = "vakh"
    user.interests = [Category.PEOPLE.value, Category.BOOKS.value]
    user.transport = Transport.WALK
    user.notify = NotifyMode.ALL
    user.pause_until = None
    user.weekly_search = None
    await session.flush()
    await session.execute(
        pg_insert(OrgMember)
        .values(org_id=demo_id("o-books"), user_id=user.id, role=OrgRole.OWNER)
        .on_conflict_do_update(
            index_elements=[OrgMember.org_id, OrgMember.user_id],
            set_={"role": OrgRole.OWNER, "revoked_at": None},
        )
    )

async def seed_history(session: AsyncSession, now: datetime) -> None:
    user = await _demo_user(session)
    assert user is not None, "seed_demo_user должен идти раньше"
    await session.execute(delete(HourLedger).where(HourLedger.user_id == user.id))
    for index, (title, days_ago, org_key, hours_raw, micro) in enumerate(HISTORY):
        hours = Decimal(hours_raw)
        org_id = demo_id(org_key)
        at = _local_noon(now, days_ago)
        if micro:
            task = await session.merge(
                MicroTask(
                    id=demo_id(f"h{index}-task"),
                    org_id=org_id,
                    title=title,
                    text=title,
                    minutes=int(hours * 60),
                    answers_needed=1,
                    active=False,
                )
            )
            answer = await session.merge(
                MicroAnswer(
                    id=demo_id(f"h{index}-answer"),
                    task_id=task.id,
                    user_id=user.id,
                    status=MicroAnswerStatus.ACCEPTED,
                    answer="Ответ из демо-данных",
                    reviewed_at=at,
                )
            )
            source, ref_id = LedgerSource.MICRO, answer.id
        else:
            starts_at = at - timedelta(hours=int(hours) + 1)
            shift = await session.merge(
                Shift(
                    id=demo_id(f"h{index}-shift"),
                    org_id=org_id,
                    title=title,
                    category=_HISTORY_CATEGORY.get(org_key, Category.PEOPLE),
                    starts_at=starts_at,
                    ends_at=starts_at + timedelta(minutes=int(hours * 60)),
                    capacity=10,
                    address=next(o[2] for o in ORGS if o[0] == org_key),
                    status=ShiftStatus.FINISHED,
                    checkin_secret=os.urandom(20),
                )
            )
            booking = await session.merge(
                Booking(
                    id=demo_id(f"h{index}-booking"),
                    shift_id=shift.id,
                    user_id=user.id,
                    status=BookingStatus.DONE,
                    checked_in_at=starts_at,
                )
            )
            source, ref_id = LedgerSource.SHIFT, booking.id
        await session.flush()
        session.add(
            HourLedger(
                user_id=user.id,
                source=source,
                ref_id=ref_id,
                hours=hours,
                org_id=org_id,
                accepted_at=at,
            )
        )
    await session.flush()
