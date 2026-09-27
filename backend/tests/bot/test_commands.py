from datetime import timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import commands, relay
from app.bot.transport import MaxRetryableError
from app.db.enums import BookingStatus, NotifyMode
from app.db.models import Booking, BotConversation, MessageRelay, Org, OrgMember
from tests.bot.conftest import (
    BotHarness,
    bot_started,
    drain,
    make_shift,
    message_callback,
    message_created,
    now,
    run_bot_updates,
    with_chat,
)
from tests.factories import add_member, make_org, make_user


async def setup_contact(db_session: AsyncSession):
    org = await make_org(db_session)
    coordinator = await make_user(db_session, first_name="Ольга")
    await add_member(db_session, org, coordinator)
    coord_chat = await with_chat(db_session, coordinator)
    user = await make_user(db_session, first_name="Алина")
    chat = await with_chat(db_session, user)
    shift = await make_shift(db_session, org)
    booking = Booking(user_id=user.id, shift_id=shift.id, status=BookingStatus.GOING)
    db_session.add(booking)
    await db_session.commit()
    return user, chat, coordinator, coord_chat, booking

async def test_contact_deeplink_starts_private_two_way_conversation(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, coordinator, coord_chat, booking = await setup_contact(db_session)
    outcome = await harness.deliver(
        bot_started(user_id=user.max_user_id, chat_id=chat, payload=f"contact_{booking.id}")
    )
    assert not outcome.failed
    assert "Напиши вопрос" in harness.transport.to_chat(chat)[0].text
    assert harness.transport.to_chat(coord_chat) == []
    conversation = await db_session.get(BotConversation, user.id)
    assert conversation is not None and conversation.relay_id
    harness.transport.reset()

    event = message_created("Где вход?", user_id=user.max_user_id, chat_id=chat)
    await harness.deliver(event)
    await harness.deliver(event)
    await drain()
    [question] = harness.transport.to_chat(coord_chat)
    assert question.text == "Алина · Разбор книг\nГде вход?"
    await harness.deliver(
        message_created(
            "Со двора", user_id=coordinator.max_user_id, chat_id=coord_chat, reply_to=question.mid
        )
    )
    await drain()
    assert harness.transport.to_chat(chat)[0].text.endswith("Со двора")

async def test_my_and_messages_list_only_own_bookings(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, coordinator, _, booking = await setup_contact(db_session)
    for command in ("my", "messages"):
        harness.transport.reset()
        await harness.deliver(bot_started(user_id=user.max_user_id, chat_id=chat, payload=command))
        [sent] = harness.transport.to_chat(chat)
        assert "Разбор книг" in sent.text
        if command == "my":
            assert "Возьми перчатки" not in sent.text
            await harness.deliver(
                message_callback(
                    f"booking:{booking.id}:upcoming:0", user_id=user.max_user_id, chat_id=chat
                )
            )
            assert "Возьми перчатки" in harness.transport.to_chat(chat)[-1].text
        assert sent.attachments
    harness.transport.reset()
    await harness.deliver(message_created("/my", user_id=coordinator.max_user_id, chat_id=999))
    assert harness.transport.to_chat(999)[0].text == commands.NO_BOOKINGS

async def test_contact_callback_and_cancel_do_not_forward_later_plain_messages(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, _, coord_chat, booking = await setup_contact(db_session)
    await harness.deliver(
        message_callback(f"contact:{booking.id}", user_id=user.max_user_id, chat_id=chat)
    )
    assert harness.transport.callbacks
    await harness.deliver(message_callback("menu:cancel", user_id=user.max_user_id, chat_id=chat))
    harness.transport.reset()
    await harness.deliver(
        message_created("Это личная заметка", user_id=user.max_user_id, chat_id=chat)
    )
    await drain()
    assert not harness.transport.to_chat(coord_chat)
    assert harness.transport.to_chat(chat)[0].text == relay.DEFAULT_REPLY

@pytest.mark.parametrize("invalid", ["other_user", "cancelled", "malformed", "no_consent"])
async def test_contact_checks_booking_ownership_status_and_consent(
    harness: BotHarness, db_session: AsyncSession, invalid: str
) -> None:
    user, chat, _, coord_chat, booking = await setup_contact(db_session)
    target = str(booking.id)
    expected = commands.NO_CONTACT
    if invalid == "other_user":
        user = await make_user(db_session)
    elif invalid == "cancelled":
        booking.status = BookingStatus.CANCELLED
    elif invalid == "malformed":
        target = "oops"
    else:
        user.consent_at = None
        expected = commands.CONSENT_REQUIRED
    await db_session.commit()
    await harness.deliver(
        bot_started(user_id=user.max_user_id, chat_id=chat, payload=f"contact_{target}")
    )
    assert harness.transport.to_chat(chat)[0].text == expected
    assert not harness.transport.to_chat(coord_chat)
    assert await db_session.scalar(select(func.count()).select_from(MessageRelay)) == 0

async def test_commands_are_never_forwarded_to_coordinator(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, _, coord_chat, booking = await setup_contact(db_session)
    await harness.deliver(
        bot_started(user_id=user.max_user_id, chat_id=chat, payload=f"contact_{booking.id}")
    )
    harness.transport.reset()
    for text in ("/help", "/unknown", "/my", "/messages"):
        await harness.deliver(message_created(text, user_id=user.max_user_id, chat_id=chat))
    await drain()
    assert not harness.transport.to_chat(coord_chat)

async def test_expired_conversation_and_unknown_reply_do_not_route_to_other_thread(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, _, coord_chat, booking = await setup_contact(db_session)
    await harness.deliver(
        bot_started(user_id=user.max_user_id, chat_id=chat, payload=f"contact_{booking.id}")
    )
    harness.transport.reset()
    await harness.deliver(
        message_created(
            "Не тому адресату", user_id=user.max_user_id, chat_id=chat, reply_to="unknown"
        )
    )
    conversation = await db_session.get(BotConversation, user.id)
    assert conversation is not None
    conversation.expires_at = now() - timedelta(seconds=1)
    await db_session.commit()
    await harness.deliver(message_created("Вчерашний чат", user_id=user.max_user_id, chat_id=chat))
    await drain()
    assert not harness.transport.to_chat(coord_chat)
    assert len(harness.transport.to_chat(chat)) == 2

@pytest.mark.parametrize("revoked", ["coordinator", "booking"])
async def test_relay_rechecks_access_before_queued_delivery(
    harness: BotHarness, db_session: AsyncSession, revoked: str
) -> None:
    user, chat, coordinator, coord_chat, booking = await setup_contact(db_session)
    await harness.deliver(
        bot_started(user_id=user.max_user_id, chat_id=chat, payload=f"contact_{booking.id}")
    )
    await harness.deliver(message_created("Где вход?", user_id=user.max_user_id, chat_id=chat))
    if revoked == "booking":
        booking.status = BookingStatus.CANCELLED
    else:
        member = (
            await db_session.scalars(select(OrgMember).where(OrgMember.user_id == coordinator.id))
        ).one()
        member.revoked_at = now()
    await db_session.commit()
    await drain()
    assert not harness.transport.to_chat(coord_chat)

async def test_reply_is_not_suppressed_by_notification_pause(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, coordinator, coord_chat, booking = await setup_contact(db_session)
    user.notify = coordinator.notify = NotifyMode.PAUSE
    await db_session.commit()
    await harness.deliver(
        bot_started(user_id=user.max_user_id, chat_id=chat, payload=f"contact_{booking.id}")
    )
    await harness.deliver(message_created("Вопрос", user_id=user.max_user_id, chat_id=chat))
    await drain()
    [question] = harness.transport.to_chat(coord_chat)
    await harness.deliver(
        message_created(
            "Ответ", user_id=coordinator.max_user_id, chat_id=coord_chat, reply_to=question.mid
        )
    )
    await drain()
    assert harness.transport.to_chat(chat)[-1].text.endswith("Ответ")

async def test_retry_reuses_thread_after_max_temporarily_unavailable(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, _, _, booking = await setup_contact(db_session)
    harness.transport.failures.append(MaxRetryableError(429, "too.many.requests"))
    result = await harness.deliver(
        bot_started(user_id=user.max_user_id, chat_id=chat, payload=f"contact_{booking.id}")
    )
    assert result.failed
    assert await run_bot_updates(now() + timedelta(hours=1))
    assert await db_session.scalar(select(func.count()).select_from(MessageRelay)) == 1
    assert len(harness.transport.to_chat(chat)) == 1

async def test_contact_does_not_pick_coordinator_from_another_organization(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, _, coord_chat, _ = await setup_contact(db_session)
    other_org = await make_org(db_session)
    other_shift = await make_shift(db_session, other_org)
    booking = Booking(user_id=user.id, shift_id=other_shift.id, status=BookingStatus.GOING)
    db_session.add(booking)
    await db_session.commit()
    await harness.deliver(
        bot_started(user_id=user.max_user_id, chat_id=chat, payload=f"contact_{booking.id}")
    )
    assert harness.transport.to_chat(chat)[0].text == commands.NO_COORDINATOR
    assert not harness.transport.to_chat(coord_chat)

async def test_group_callback_never_exposes_personal_bookings(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, _, _, _ = await setup_contact(db_session)
    event = message_callback("menu:my", user_id=user.max_user_id, chat_id=chat)
    event["message"]["recipient"]["chat_type"] = "chat"
    await harness.deliver(event)
    assert harness.transport.sent == []

async def test_callback_account_is_author_of_click_not_bot_author_of_message(
    harness: BotHarness,
) -> None:
    from maxapi.methods.types.getted_updates import process_update_webhook

    from app.bot.updates import _event_user_id

    event = message_callback("menu:help", user_id=42, chat_id=800)
    event["message"]["sender"]["user_id"] = 999
    event["message"]["sender"]["is_bot"] = True
    parsed = await process_update_webhook(event_json=event, bot=harness.runtime.bot)
    assert parsed is not None
    assert _event_user_id(parsed) == 42

async def test_booking_pages_include_distant_events_and_history(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    from app.db.enums import ShiftStatus
    from app.db.models import Shift

    user, chat, _, _, booking = await setup_contact(db_session)
    first = await db_session.get(Shift, booking.shift_id)
    org = await db_session.get(Org, first.org_id)
    for i in range(12):
        shift = await make_shift(
            db_session, org, starts_at=now() + timedelta(days=i + 2), title=f"Будущее {i}"
        )
        db_session.add(Booking(user_id=user.id, shift_id=shift.id, status=BookingStatus.GOING))
    first.starts_at = now() - timedelta(days=3)
    first.ends_at = now() - timedelta(days=3) + timedelta(hours=1)
    first.status = ShiftStatus.FINISHED
    booking.status = BookingStatus.DONE
    await db_session.commit()
    await harness.deliver(
        message_callback("menu:my:upcoming:2", user_id=user.max_user_id, chat_id=chat)
    )
    [sent] = harness.transport.to_chat(chat)
    assert "Будущее 11" in sent.text and "Будущее 0 ·" not in sent.text
    assert any(b.payload == "menu:my:upcoming:1" for b in sent.buttons())
    harness.transport.reset()
    await harness.deliver(
        message_callback("menu:my:history:0", user_id=user.max_user_id, chat_id=chat)
    )
    assert "Разбор книг" in harness.transport.to_chat(chat)[0].text
    assert "Завершено" in harness.transport.to_chat(chat)[0].text
    harness.transport.reset()
    await harness.deliver(
        message_callback("menu:messages:history:0", user_id=user.max_user_id, chat_id=chat)
    )
    assert any(
        b.payload == f"contact:{booking.id}" for b in harness.transport.to_chat(chat)[0].buttons()
    )
    await harness.deliver(
        message_callback(f"contact:{booking.id}", user_id=user.max_user_id, chat_id=chat)
    )
    assert "Напиши вопрос" in harness.transport.to_chat(chat)[-1].text

async def test_back_and_booking_list_exit_conversation(
    harness: BotHarness, db_session: AsyncSession
) -> None:
    user, chat, _, coord_chat, booking = await setup_contact(db_session)
    for command in ("back", "messages", "my"):
        await harness.deliver(
            message_callback(f"contact:{booking.id}", user_id=user.max_user_id, chat_id=chat)
        )
        await harness.deliver(
            message_callback(f"menu:{command}", user_id=user.max_user_id, chat_id=chat)
        )
        await harness.deliver(
            message_created("Уже не вопрос координатору", user_id=user.max_user_id, chat_id=chat)
        )
        await drain()
        assert not harness.transport.to_chat(coord_chat)
        assert harness.transport.to_chat(chat)[-1].text == relay.DEFAULT_REPLY

async def test_browser_registration_keeps_app_destination(harness: BotHarness, monkeypatch) -> None:
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_bot_username", "vremya_test_bot")
    await harness.deliver(bot_started(user_id=707070, chat_id=123, payload="app_deal_demo-id"))
    [message] = harness.transport.to_chat(123)
    [button] = message.buttons()
    assert button.payload == "deal_demo-id"
    assert button.web_app == "vremya_test_bot"
