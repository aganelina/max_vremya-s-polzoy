from __future__ import annotations

from typing import Any

from maxapi.enums.attachment import AttachmentType
from maxapi.types.attachments.attachment import ButtonsPayload
from maxapi.types.attachments.buttons import CallbackButton, LinkButton, OpenAppButton
from maxapi.types.attachments.buttons.attachment_button import AttachmentButton

from app.config import get_settings

FIND_DEAL = "Найти дело"
OPEN = "Открыть"

URGENT_GO_PREFIX = "urgent_go:"
CONTACT_PREFIX = "contact:"
BOOKING_PREFIX = "booking:"

def keyboard(rows: list[list[Any]]) -> AttachmentButton:
    return AttachmentButton(
        type=AttachmentType.INLINE_KEYBOARD,
        payload=ButtonsPayload(buttons=rows),
        bot=None,
    )

def app_button(text: str = OPEN, startapp: str | None = None) -> Any:
    settings = get_settings()
    if settings.max_bot_username:
        return OpenAppButton(text=text, web_app=settings.max_bot_username, payload=startapp)
    base = settings.public_base_url.rstrip("/")
    return LinkButton(text=text, url=f"{base}/?startapp={startapp}" if startapp else base)

def open_app(text: str = OPEN, startapp: str | None = None) -> AttachmentButton:
    return keyboard([[app_button(text, startapp)]])

def urgent_go(call_id: str) -> AttachmentButton:
    return keyboard([[CallbackButton(text="Иду", payload=f"{URGENT_GO_PREFIX}{call_id}")]])

def menu() -> AttachmentButton:
    return keyboard(
        [
            [app_button("Открыть приложение")],
            [
                CallbackButton(text="Мои записи", payload="menu:my"),
                CallbackButton(text="Координатор", payload="menu:messages"),
            ],
            [CallbackButton(text="Помощь", payload="menu:help")],
        ]
    )

def back_menu() -> Any:
    return CallbackButton(text="‹ В меню", payload="menu:back")

def booking_actions(
    booking_id: str, shift_id: str, back: str, *, contact: bool
) -> AttachmentButton:
    rows = [[app_button("Открыть событие", f"deal_{shift_id}")]]
    if contact:
        rows.append(
            [CallbackButton(text="Написать координатору", payload=f"{CONTACT_PREFIX}{booking_id}")]
        )
    rows.append([CallbackButton(text="‹ К записям", payload=f"menu:{back}"), back_menu()])
    return keyboard(rows)

def end_conversation() -> AttachmentButton:
    return keyboard(
        [
            [
                CallbackButton(text="‹ К выбору смены", payload="menu:messages"),
                CallbackButton(text="Завершить диалог", payload="menu:cancel"),
            ]
        ]
    )
