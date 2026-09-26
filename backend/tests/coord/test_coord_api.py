from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import current_time
from app.db.enums import (
    BookingStatus,
    LedgerSource,
    MicroAnswerStatus,
    OrgRole,
    OrgStatus,
    ShiftStatus,
)
from app.db.models import (
    FreeWindow,
    HourLedger,
    Job,
    Message,
    MicroAnswer,
    MicroTask,
    Org,
    OrgInvite,
    OrgMember,
    Shift,
    UrgentRecipient,
)
from app.domain import checkin_code
from app.domain.coord import CoordError
from app.domain.org_access import accept_org_invite
from tests.conftest import NOW
from tests.coord.conftest import Team, book, make_shift
from tests.factories import add_member, make_org, make_user
from tests.support import dev


async def _jobs(session: AsyncSession, kind: str) -> list[Job]:
    return list(await session.scalars(select(Job).where(Job.kind == kind)))

async def test_non_coordinator_forbidden(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    user = await make_user(db_session)
    r = await client.get("/coord/home", headers=dev(user))
    assert r.status_code == 403 and r.json() == {"code": "not_coordinator"}

async def test_home_next_and_open_shifts(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    first = await make_shift(db_session, team.org, starts_at=NOW + timedelta(hours=3))
    second = await make_shift(db_session, team.org, starts_at=NOW + timedelta(days=2))
    await make_shift(db_session, team.org, status=ShiftStatus.CANCELLED)
    other = await make_org(db_session)
    await make_shift(db_session, other)
    await book(db_session, first, await make_user(db_session))

    r = await client.get("/coord/home", headers=dev(team.owner))
    assert r.status_code == 200
    body = r.json()
    assert body["next"]["shift"]["id"] == str(first.id)
    assert body["next"]["going"] == 1
    assert body["next"]["shift"]["booked"] == 1
    assert body["next"]["shift"]["org"]["verified"] is True
    assert [s["id"] for s in body["shifts"]] == [str(second.id)]

async def test_attendance_statuses_and_foreign_shift_404(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    shift = await make_shift(db_session, team.org)
    came = await make_user(db_session, first_name="Алина")
    late = await make_user(db_session, first_name="Тимур")
    waiting = await make_user(db_session, first_name="Софья")
    gone = await make_user(db_session, first_name="Ушла")
    await book(db_session, shift, came, BookingStatus.CHECKED_IN, shift.starts_at)
    await book(
        db_session, shift, late, BookingStatus.CHECKED_IN, shift.starts_at + timedelta(minutes=12)
    )
    await book(db_session, shift, waiting)
    await book(db_session, shift, gone, BookingStatus.CANCELLED)

    r = await client.get(f"/coord/shifts/{shift.id}/attendance", headers=dev(team.owner))
    assert r.status_code == 200
    people = r.json()["participants"]
    assert [(p["firstName"], p["status"]) for p in people] == [
        ("Алина", "came"),
        ("Тимур", "late"),
        ("Софья", "booked"),
    ]
    assert people[0]["id"] == str(came.id)

    foreign = await make_shift(db_session, await make_org(db_session))
    r = await client.get(f"/coord/shifts/{foreign.id}/attendance", headers=dev(team.owner))
    assert r.status_code == 404
    r = await client.get("/coord/shifts/not-a-uuid/attendance", headers=dev(team.owner))
    assert r.status_code == 404

async def test_manual_mark_and_undo(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    shift = await make_shift(db_session, team.org)
    user = await make_user(db_session)
    await book(db_session, shift, user)
    url = f"/coord/shifts/{shift.id}/participants/{user.id}/manual"

    r = await client.put(url, headers=dev(team.owner))
    assert r.status_code == 200
    p = r.json()["participants"][0]
    assert p["status"] == "manual" and p["checkedInAt"] is not None

    r = await client.delete(url, headers=dev(team.owner))
    assert r.json()["participants"][0]["status"] == "booked"

    stranger = await make_user(db_session)
    r = await client.put(
        f"/coord/shifts/{shift.id}/participants/{stranger.id}/manual", headers=dev(team.owner)
    )
    assert r.status_code == 404

async def test_manual_mark_on_finished_shift_credits_hours(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    shift = await make_shift(
        db_session, team.org, starts_at=NOW - timedelta(hours=3), status=ShiftStatus.FINISHED
    )
    user = await make_user(db_session)
    await book(db_session, shift, user, BookingStatus.NO_SHOW)
    url = f"/coord/shifts/{shift.id}/participants/{user.id}/manual"
    assert (await client.put(url, headers=dev(team.owner))).status_code == 200
    hours = await db_session.scalar(select(HourLedger.hours).where(HourLedger.user_id == user.id))
    assert hours == Decimal("1.5")
    await client.delete(url, headers=dev(team.owner))
    left = await db_session.scalar(
        select(func.count()).select_from(HourLedger).where(HourLedger.user_id == user.id)
    )
    assert left == 0

async def test_checkin_code_is_totp(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    shift = await make_shift(db_session, team.org)
    r = await client.get(f"/coord/shifts/{shift.id}/code", headers=dev(team.owner))
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == checkin_code.totp(shift.checkin_secret, NOW)
    assert body["qrPayload"] == f"vremya:checkin:{body['code']}"
    assert body["expiresAt"].startswith("2026-09-29T09:01:00")

async def test_cancel_shift_cancels_going_and_notifies(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    shift = await make_shift(db_session, team.org)
    user = await make_user(db_session)
    booking = await book(db_session, shift, user)
    r = await client.post(f"/coord/shifts/{shift.id}/cancel", headers=dev(team.owner))
    assert r.status_code == 204
    await db_session.refresh(shift)
    await db_session.refresh(booking)
    assert shift.status is ShiftStatus.CANCELLED
    assert booking.status is BookingStatus.CANCELLED
    jobs = await _jobs(db_session, "notify.shift_cancelled")
    assert jobs[0].payload == {"shift_id": str(shift.id), "user_ids": [str(user.id)]}

    started = await make_shift(db_session, team.org, starts_at=NOW - timedelta(minutes=5))
    r = await client.post(f"/coord/shifts/{started.id}/cancel", headers=dev(team.owner))
    assert r.status_code == 409 and r.json()["code"] == "shift_started"

async def test_create_shift(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    payload = {
        "title": "Мастер-класс",
        "date": "2026-10-01",
        "time": "18:30",
        "durationMin": 90,
        "capacity": 6,
        "category": "books",
        "place": "org",
        "instructions": "Спроси Гульнару",
        "quorum": True,
    }
    r = await client.post("/coord/shifts", json=payload, headers=dev(team.owner))
    assert r.status_code == 200
    body = r.json()
    assert body["startsAt"] == "2026-10-01T18:30:00+03:00"
    assert body["address"] == team.org.address
    assert body["booked"] == 0 and body["quorum"] is True and body["status"] == "open"
    shift = await db_session.get(Shift, body["id"])
    assert shift is not None and len(shift.checkin_secret) == 20
    assert (await _jobs(db_session, "shift.offer"))[0].payload == {"shift_id": body["id"]}

    r = await client.post(
        "/coord/shifts", json={**payload, "date": "2026-09-28"}, headers=dev(team.owner)
    )
    assert r.status_code == 422 and r.json()["code"] == "starts_in_past"
    r = await client.post(
        "/coord/shifts", json={**payload, "durationMin": 500}, headers=dev(team.owner)
    )
    assert r.json()["code"] == "invalid_duration"

async def test_urgent_call_picks_recipients(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    windowed = await make_user(db_session, first_name="Окно")
    db_session.add(
        FreeWindow(
            user_id=windowed.id,
            starts_at=NOW - timedelta(minutes=10),
            ends_at=NOW + timedelta(hours=3),
        )
    )
    await db_session.commit()
    others = [await make_user(db_session) for _ in range(20)]
    busy_shift = await make_shift(
        db_session, await make_org(db_session), starts_at=NOW + timedelta(minutes=20)
    )
    await book(db_session, busy_shift, others[0])

    r = await client.post(
        "/coord/urgent",
        json={
            "what": "Разгрузить машину",
            "where": "ул. Баумана, 19",
            "startInMin": 30,
            "people": 3,
        },
        headers=dev(team.owner),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["reached"] == 15 and body["responses"] == [] and body["people"] == 3
    recipients = set(await db_session.scalars(select(UrgentRecipient.user_id)))
    assert windowed.id in recipients
    assert others[0].id not in recipients and team.owner.id not in recipients
    shift = await db_session.get(Shift, body["shiftId"])
    assert shift is not None and shift.starts_at == NOW + timedelta(minutes=30)
    assert shift.capacity == 3
    assert (await _jobs(db_session, "notify.urgent_call"))[0].payload == {"call_id": body["id"]}

    rec = await db_session.get(UrgentRecipient, (body["id"], windowed.id))
    assert rec is not None
    rec.responded_at = NOW + timedelta(minutes=2)
    await db_session.commit()
    r = await client.get(f"/coord/urgent/{body['id']}", headers=dev(team.owner))
    assert r.json()["responses"][0]["name"] == "Окно"

    other_owner = await make_user(db_session)
    await add_member(db_session, await make_org(db_session), other_owner, role=OrgRole.OWNER)
    r = await client.get(f"/coord/urgent/{body['id']}", headers=dev(other_owner))
    assert r.status_code == 404

async def _sent_answer(session: AsyncSession, team: Team, minutes: int = 30) -> MicroAnswer:
    task = MicroTask(
        org_id=team.org.id, title="Письмо", text="Напиши", minutes=minutes, answers_needed=3
    )
    session.add(task)
    await session.flush()
    author = await make_user(session, first_name="Камила")
    answer = MicroAnswer(
        task_id=task.id,
        user_id=author.id,
        status=MicroAnswerStatus.SENT,
        answer="Здравствуйте, это письмо",
    )
    session.add(answer)
    await session.commit()
    return answer

async def test_review_accept_and_undo(
    app: FastAPI, client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    answer = await _sent_answer(db_session, team)
    r = await client.get("/coord/reviews", headers=dev(team.owner))
    assert r.json()["items"] == [
        {
            "id": str(answer.id),
            "authorName": "Камила",
            "minutes": 30,
            "task": "Письмо",
            "answer": "Здравствуйте, это письмо",
        }
    ]
    r = await client.post(
        f"/coord/reviews/{answer.id}", json={"verdict": "accept"}, headers=dev(team.owner)
    )
    assert r.status_code == 204
    ledger = await db_session.scalar(select(HourLedger).where(HourLedger.ref_id == answer.id))
    assert ledger is not None and ledger.hours == Decimal("0.5")
    assert ledger.source is LedgerSource.MICRO
    r = await client.get("/coord/reviews", headers=dev(team.owner))
    assert r.json()["items"] == [] and r.json()["acceptedToday"] == 1
    assert len(await _jobs(db_session, "notify.micro_reviewed")) == 1

    r = await client.post(
        f"/coord/reviews/{answer.id}", json={"verdict": "accept"}, headers=dev(team.owner)
    )
    assert r.status_code == 409

    r = await client.delete(f"/coord/reviews/{answer.id}", headers=dev(team.owner))
    assert r.status_code == 204
    await db_session.refresh(answer)
    assert answer.status is MicroAnswerStatus.SENT
    assert await db_session.scalar(select(func.count()).select_from(HourLedger)) == 0
    assert await _jobs(db_session, "notify.micro_reviewed") == []

    r = await client.post(
        f"/coord/reviews/{answer.id}", json={"verdict": "return"}, headers=dev(team.owner)
    )
    assert r.status_code == 422 and r.json()["code"] == "note_required"
    r = await client.post(
        f"/coord/reviews/{answer.id}",
        json={"verdict": "return", "note": "Добавь вопрос"},
        headers=dev(team.owner),
    )
    assert r.status_code == 204
    app.dependency_overrides[current_time] = lambda: NOW + timedelta(minutes=11)
    r = await client.delete(f"/coord/reviews/{answer.id}", headers=dev(team.owner))
    assert r.status_code == 409 and r.json()["code"] == "undo_expired"

async def test_review_of_other_org_404(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    answer = await _sent_answer(db_session, team)
    other = await make_user(db_session)
    await add_member(db_session, await make_org(db_session), other, role=OrgRole.OWNER)
    r = await client.post(
        f"/coord/reviews/{answer.id}", json={"verdict": "accept"}, headers=dev(other)
    )
    assert r.status_code == 404

async def test_micro_task_crud(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    payload = {
        "title": "Подбери книги",
        "text": "Пять книг для подростков",
        "minutes": 10,
        "answersNeeded": 5,
        "deadline": "2026-10-10T18:00:00+03:00",
    }
    r = await client.post("/coord/micro-tasks", json=payload, headers=dev(team.owner))
    assert r.status_code == 200
    task = r.json()
    assert task["active"] is True and task["pending"] == 0 and task["answersNeeded"] == 5
    r = await client.post(
        "/coord/micro-tasks", json={**payload, "minutes": 90}, headers=dev(team.owner)
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_minutes"

    r = await client.patch(
        f"/coord/micro-tasks/{task['id']}", json={"active": False}, headers=dev(team.owner)
    )
    assert r.json()["active"] is False
    r = await client.get("/coord/micro-tasks", headers=dev(team.owner))
    assert [t["id"] for t in r.json()] == [task["id"]]

    other = await make_user(db_session)
    await add_member(db_session, await make_org(db_session), other, role=OrgRole.OWNER)
    r = await client.patch(
        f"/coord/micro-tasks/{task['id']}", json={"active": True}, headers=dev(other)
    )
    assert r.status_code == 404

@pytest.mark.parametrize("days_ago", [3, 35, 44])
async def test_metrics_own_org_and_pilot_average(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team, days_ago: int
) -> None:
    past = await make_shift(
        db_session, team.org, starts_at=NOW - timedelta(days=days_ago), status=ShiftStatus.FINISHED
    )
    other_org = await make_org(db_session)
    other_org.name = "Чужая"
    await db_session.commit()
    other_past = await make_shift(
        db_session,
        other_org,
        starts_at=NOW - timedelta(days=days_ago + 1),
        status=ShiftStatus.FINISHED,
    )
    for shift in (past, other_past):
        for came in (True, True, True, False):
            user = await make_user(db_session)
            b = await book(
                db_session,
                shift,
                user,
                BookingStatus.DONE if came else BookingStatus.NO_SHOW,
                shift.starts_at if came else None,
            )
            b.created_at = NOW - timedelta(days=days_ago + 2)
            if came:
                db_session.add(
                    HourLedger(
                        user_id=user.id,
                        source=LedgerSource.SHIFT,
                        ref_id=b.id,
                        hours=Decimal("1.5"),
                        org_id=shift.org_id,
                        accepted_at=shift.ends_at,
                    )
                )
            await db_session.commit()

    r = await client.get("/coord/metrics", headers=dev(team.owner))
    assert r.status_code == 200
    body = r.json()
    assert body["periodLabel"] == "Пилот · за 6 недель"
    if days_ago > 42:
        assert body["hours"] == 0 and body["participants"] == 0
        assert all(f["value"] == 0 for f in body["funnel"])
        assert body["orgs"] == []
        return
    assert body["hours"] == 9.0 and body["participants"] == 6
    assert [f["value"] for f in body["funnel"]] == [8, 8, 6]
    assert body["orgs"] == [
        {"name": team.org.name, "attendance": 0.75, "hours": 4.5},
        {"name": "В среднем по пилоту", "attendance": 0.75, "hours": 4.5},
    ]

async def test_access_invite_revoke(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    coord = await make_user(db_session, first_name="Ринат")
    await add_member(db_session, team.org, coord)
    await make_shift(db_session, team.org)

    r = await client.get("/coord/access", headers=dev(team.owner))
    body = r.json()
    assert body["shiftsThisMonth"] == 1 and body["invite"] is None
    assert body["coordinators"][0] == {
        "id": str(team.owner.id),
        "name": "Гульнара",
        "owner": True,
        "me": True,
        "revoked": False,
    }

    r = await client.post("/coord/access/invites", headers=dev(team.owner))
    invite = r.json()["invite"]
    assert "startapp=org_" in invite["link"]
    assert invite["expiresAt"].startswith("2026-10-06T09:00:00")

    r = await client.patch(
        f"/coord/access/{coord.id}", json={"revoked": True}, headers=dev(team.owner)
    )
    assert r.json()["coordinators"][1]["revoked"] is True
    r = await client.get("/coord/home", headers=dev(coord))
    assert r.status_code == 403

    r = await client.patch(
        f"/coord/access/{team.owner.id}", json={"revoked": True}, headers=dev(team.owner)
    )
    assert r.status_code == 409 and r.json()["code"] == "cannot_revoke_self"

    r = await client.patch(
        f"/coord/access/{coord.id}", json={"revoked": False}, headers=dev(team.owner)
    )
    assert r.json()["coordinators"][1]["revoked"] is False
    r = await client.post("/coord/access/invites", headers=dev(coord))
    assert r.status_code == 403 and r.json()["code"] == "not_owner"

async def test_accept_org_invite(db_session: AsyncSession, team: Team) -> None:
    org_id = team.org.id
    invite = OrgInvite(org_id=org_id, token="tok", expires_at=NOW + timedelta(days=7))
    db_session.add(invite)
    await db_session.commit()
    user = await make_user(db_session)
    org = await accept_org_invite(db_session, "org_tok", user, NOW)
    await db_session.commit()
    assert org.id == team.org.id
    member = await db_session.get(OrgMember, (team.org.id, user.id))
    assert member is not None and member.role is OrgRole.COORDINATOR
    with pytest.raises(CoordError) as exc:
        await accept_org_invite(db_session, "tok", await make_user(db_session), NOW)
    assert exc.value.code == "invite_used"
    await db_session.rollback()

    expired = OrgInvite(org_id=org_id, token="old", expires_at=NOW - timedelta(seconds=1))
    db_session.add(expired)
    await db_session.commit()
    with pytest.raises(CoordError) as exc:
        await accept_org_invite(db_session, "old", await make_user(db_session), NOW)
    assert exc.value.code == "invite_expired"
    await db_session.rollback()

async def test_attendance_csv(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    shift = await make_shift(db_session, team.org, title="Книги")
    user = await make_user(db_session, first_name="Алина")
    await book(db_session, shift, user, BookingStatus.CHECKED_IN, shift.starts_at)
    r = await client.get(
        "/coord/attendance.csv",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=dev(team.owner),
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8")
    assert text.startswith("﻿date,shift,name,status,checked_in_at,hours\r\n")
    assert "2026-09-30,Книги,Алина,came,2026-09-30T12:00+03:00," in text

    r = await client.get(
        "/coord/attendance.csv",
        params={"from": "2026-10-01", "to": "2026-09-01"},
        headers=dev(team.owner),
    )
    assert r.status_code == 422

async def test_audiences_and_messages(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    shift = await make_shift(db_session, team.org)
    await book(
        db_session,
        shift,
        await make_user(db_session, first_name="Алина"),
        BookingStatus.CHECKED_IN,
        shift.starts_at,
    )
    await book(db_session, shift, await make_user(db_session, first_name="Софья"))
    r = await client.get(f"/coord/shifts/{shift.id}/audiences", headers=dev(team.owner))
    assert r.json() == [
        {"key": "all", "names": ["Алина", "Софья"]},
        {"key": "waiting", "names": ["Софья"]},
        {"key": "came", "names": ["Алина"]},
    ]
    r = await client.post(
        f"/coord/shifts/{shift.id}/messages",
        json={"audience": "waiting", "text": "Вход со двора"},
        headers=dev(team.owner),
    )
    assert r.json() == {"sent": 1}
    message = await db_session.scalar(select(Message))
    assert message is not None and message.sent_count == 1
    jobs = await _jobs(db_session, "notify.coord_message")
    assert jobs[0].payload == {"message_id": str(message.id)}

    r = await client.post(
        f"/coord/shifts/{shift.id}/messages",
        json={"audience": "all", "text": "x" * 501},
        headers=dev(team.owner),
    )
    assert r.status_code == 422
    foreign = await make_shift(db_session, await make_org(db_session))
    r = await client.get(f"/coord/shifts/{foreign.id}/audiences", headers=dev(team.owner))
    assert r.status_code == 404

async def test_transfer_ownership_then_former_owner_can_delete(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    coord = await make_user(db_session, first_name="Ринат")
    await add_member(db_session, team.org, coord)

    r = await client.delete("/me", headers=dev(team.owner))
    assert r.status_code == 409 and r.json()["code"] == "last_owner"

    r = await client.post(f"/coord/access/{team.owner.id}/owner", headers=dev(team.owner))
    assert r.status_code == 409 and r.json()["code"] == "cannot_transfer_to_self"
    r = await client.post(f"/coord/access/{team.owner.id}/owner", headers=dev(coord))
    assert r.status_code == 403 and r.json()["code"] == "not_owner"

    r = await client.post(f"/coord/access/{coord.id}/owner", headers=dev(team.owner))
    assert r.status_code == 200
    roles = {c["name"]: c["owner"] for c in r.json()["coordinators"]}
    assert roles == {"Гульнара": False, "Ринат": True}
    r = await client.post("/coord/access/invites", headers=dev(team.owner))
    assert r.status_code == 403
    assert (await client.delete("/me", headers=dev(team.owner))).status_code == 204

async def test_transfer_to_revoked_member_404(
    client: httpx.AsyncClient, db_session: AsyncSession, team: Team
) -> None:
    coord = await make_user(db_session, first_name="Ринат")
    await add_member(db_session, team.org, coord)
    await client.patch(f"/coord/access/{coord.id}", json={"revoked": True}, headers=dev(team.owner))
    r = await client.post(f"/coord/access/{coord.id}/owner", headers=dev(team.owner))
    assert r.status_code == 404 and r.json()["code"] == "member_not_found"

async def test_rejected_applicant_can_delete_profile(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    applicant = await make_user(db_session)
    org = await make_org(db_session, status=OrgStatus.REJECTED)
    await add_member(db_session, org, applicant, role=OrgRole.OWNER)
    org_id = org.id

    assert (await client.delete("/me", headers=dev(applicant))).status_code == 204
    db_session.expunge_all()
    assert await db_session.get(Org, org_id) is None
