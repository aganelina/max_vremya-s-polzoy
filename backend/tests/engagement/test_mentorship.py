from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import BookingStatus, Category, MentorRequestStatus
from app.db.models import Booking, Job, MentorRequest, MentorSettings, Org, User
from app.domain.mentorship import create_mentor_requests_for_booking
from tests.conftest import NOW
from tests.engagement.helpers import book, make_shift
from tests.factories import done_booking, make_org, make_user
from tests.support import dev

MENTORSHIP_KEYS = {"eligible", "dealsDone", "dealsRequired", "accepting", "requests", "pairs"}
DEAL_KEYS = {
    "id",
    "title",
    "org",
    "category",
    "startsAt",
    "endsAt",
    "hours",
    "address",
    "description",
    "travelMin",
    "capacity",
    "quorum",
    "taken",
    "goingInitials",
    "checkInFrom",
    "checkInTo",
    "cancelUntil",
    "instructionsAt",
    "myBooking",
}

async def make_mentor(
    session: AsyncSession, org: Org, *, interests: list[str], accepting: bool = True
) -> User:
    mentor = await make_user(session, first_name="Алина")
    mentor.interests = interests
    for i in range(3):
        await done_booking(session, org, mentor, NOW - timedelta(days=10 + i))
    session.add(MentorSettings(user_id=mentor.id, accepting=accepting))
    await session.commit()
    return mentor

async def newbie_request(
    session: AsyncSession, org: Org, mentor: User, *, capacity: int = 5
) -> MentorRequest:
    newbie = await make_user(session, first_name="Камила")
    shift = await make_shift(session, org, NOW + timedelta(days=1), capacity=capacity)
    await book(session, shift, newbie)
    request = MentorRequest(newbie_id=newbie.id, shift_id=shift.id, mentor_id=mentor.id)
    session.add(request)
    await session.commit()
    return request

async def test_not_eligible(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    resp = await client.get("/mentorship", headers=dev(user))
    assert resp.status_code == 200
    assert resp.json() == {
        "eligible": False,
        "dealsDone": 0,
        "dealsRequired": 3,
        "accepting": False,
        "requests": [],
        "pairs": [],
    }
    patch = await client.patch("/mentorship", json={"accepting": True}, headers=dev(user))
    assert patch.status_code == 403
    assert patch.json() == {"code": "not_eligible"}

async def test_toggle_accepting(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    mentor = await make_mentor(db_session, org, interests=["people"], accepting=False)
    await newbie_request(db_session, org, mentor)
    off = (await client.get("/mentorship", headers=dev(mentor))).json()
    assert off["eligible"] is True and off["accepting"] is False and off["requests"] == []
    on = await client.patch("/mentorship", json={"accepting": True}, headers=dev(mentor))
    assert on.status_code == 200
    body = on.json()
    assert set(body) == MENTORSHIP_KEYS
    assert body["accepting"] is True and body["dealsDone"] == 3
    request = body["requests"][0]
    assert request["newbieName"] == "Камила"
    assert set(request["deal"]) == DEAL_KEYS
    assert request["deal"]["taken"] == 1 and request["deal"]["goingInitials"] == ["К"]
    assert request["deal"]["myBooking"] is None and request["deal"]["travelMin"] is None
    assert request["deal"]["hours"] == 1

async def test_accept_books_mentor(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    mentor = await make_mentor(db_session, org, interests=["people"])
    other = await make_mentor(db_session, org, interests=["people"])
    request = await newbie_request(db_session, org, mentor)
    sibling = MentorRequest(
        newbie_id=request.newbie_id, shift_id=request.shift_id, mentor_id=other.id
    )
    db_session.add(sibling)
    await db_session.commit()

    resp = await client.post(f"/mentorship/requests/{request.id}/accept", headers=dev(mentor))
    assert resp.status_code == 200
    body = resp.json()
    assert body["requests"] == []
    assert body["pairs"][0]["id"] == str(request.id)
    assert body["pairs"][0]["newbieName"] == "Камила"
    booking = await db_session.scalar(
        select(Booking).where(Booking.user_id == mentor.id, Booking.shift_id == request.shift_id)
    )
    assert booking is not None and booking.status is BookingStatus.GOING
    await db_session.refresh(sibling)
    assert sibling.status is MentorRequestStatus.EXPIRED

    again = await client.post(f"/mentorship/requests/{request.id}/accept", headers=dev(mentor))
    assert again.status_code == 409
    assert again.json() == {"code": "request_closed"}

async def test_accept_full_shift(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    mentor = await make_mentor(db_session, org, interests=["people"])
    request = await newbie_request(db_session, org, mentor, capacity=1)
    resp = await client.post(f"/mentorship/requests/{request.id}/accept", headers=dev(mentor))
    assert resp.status_code == 409
    assert resp.json() == {"code": "seat_taken"}

async def test_accept_time_conflict(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    mentor = await make_mentor(db_session, org, interests=["people"])
    request = await newbie_request(db_session, org, mentor)
    busy = await make_shift(db_session, org, NOW + timedelta(days=1, minutes=30))
    await book(db_session, busy, mentor)
    resp = await client.post(f"/mentorship/requests/{request.id}/accept", headers=dev(mentor))
    assert resp.status_code == 409
    assert resp.json() == {"code": "time_conflict"}

async def test_decline(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    mentor = await make_mentor(db_session, org, interests=["people"])
    request = await newbie_request(db_session, org, mentor)
    stranger = await make_mentor(db_session, org, interests=["people"])
    foreign = await client.post(f"/mentorship/requests/{request.id}/decline", headers=dev(stranger))
    assert foreign.status_code == 404
    resp = await client.post(f"/mentorship/requests/{request.id}/decline", headers=dev(mentor))
    assert resp.status_code == 200
    assert resp.json()["requests"] == []
    await db_session.refresh(request)
    assert request.status is MentorRequestStatus.DECLINED

async def test_create_requests_for_first_booking(db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    matching = await make_mentor(db_session, org, interests=["animals"])
    by_category = await make_mentor(db_session, org, interests=["ecology"])
    await make_mentor(db_session, org, interests=["books"])
    await make_mentor(db_session, org, interests=["animals"], accepting=False)
    newbie = await make_user(db_session)
    newbie.interests = ["animals"]
    await db_session.commit()
    shift = await make_shift(db_session, org, NOW + timedelta(days=1), category=Category.ECOLOGY)
    booking = await book(db_session, shift, newbie)

    created = await create_mentor_requests_for_booking(db_session, booking)
    await db_session.commit()
    assert {r.mentor_id for r in created} == {matching.id, by_category.id}
    jobs = (await db_session.scalars(select(Job).where(Job.kind == "notify.mentor_request"))).all()
    assert {j.payload["request_id"] for j in jobs} == {str(r.id) for r in created}
    assert await create_mentor_requests_for_booking(db_session, booking) == []

    shift2 = await make_shift(db_session, org, NOW + timedelta(days=2))
    second = await book(db_session, shift2, newbie)
    assert await create_mentor_requests_for_booking(db_session, second) == []
