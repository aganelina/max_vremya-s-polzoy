from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Protocol

from aiohttp import ClientError
from maxapi.enums.upload_type import UploadType
from maxapi.exceptions import InvalidToken, MaxConnection, MaxError, MaxUploadFileFailed
from maxapi.exceptions import MaxApiError as LibMaxApiError
from maxapi.types.attachments import Attachment, AttachmentUpload
from maxapi.types.input_media import InputMedia, InputMediaBuffer

from app.bot.throttle import MaxThrottle

if TYPE_CHECKING:
    from maxapi import Bot

class MaxApiError(Exception):

    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code
        super().__init__(f"MAX API error {status} {code}")

class MaxRetryableError(MaxApiError):
    pass

class MaxNotConfiguredError(MaxRetryableError):

    def __init__(self) -> None:
        super().__init__(503, "bot_not_configured")

OutgoingAttachment = Any

class MaxTransport(Protocol):
    async def send_message(
        self,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        text: str,
        attachments: list[OutgoingAttachment] | None = None,
    ) -> str:
        ...

    async def send_file(
        self,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        data: bytes,
        filename: str,
        text: str | None = None,
    ) -> str:
        ...

    async def answer_callback(self, callback_id: str, *, notification: str) -> None: ...

def translate(exc: BaseException) -> MaxApiError:
    if isinstance(exc, MaxApiError):
        return exc
    if isinstance(exc, InvalidToken):
        return MaxApiError(401, "invalid_token")
    if isinstance(exc, LibMaxApiError):
        raw = exc.raw
        code = str(raw.get("code") or "max_api_error") if isinstance(raw, dict) else "max_api_error"
        if exc.code == 429 or exc.code >= 500:
            return MaxRetryableError(exc.code, code)
        return MaxApiError(exc.code, code)
    if isinstance(exc, MaxConnection | MaxUploadFileFailed | ClientError | TimeoutError):
        return MaxRetryableError(503, "connection_error")
    if isinstance(exc, MaxError):
        return MaxApiError(502, "max_error")
    return MaxApiError(502, "max_error")

def _target(chat_id: int | None, user_id: int | None) -> int:
    if (chat_id is None) == (user_id is None):
        raise ValueError("нужно указать ровно один из chat_id или user_id")
    return chat_id if chat_id is not None else int(user_id or 0)

class MaxapiTransport:

    def __init__(self, bot: Bot, *, throttle: MaxThrottle | None = None) -> None:
        self._bot = bot
        self._throttle = throttle or MaxThrottle()

    async def send_message(
        self,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        text: str,
        attachments: list[OutgoingAttachment] | None = None,
    ) -> str:
        await self._throttle.acquire(_target(chat_id, user_id))
        try:
            sent = await self._bot.send_message(
                chat_id=chat_id, user_id=user_id, text=text, attachments=attachments or None
            )
        except Exception as exc:
            raise translate(exc) from exc
        return _mid(sent)

    async def send_file(
        self,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        data: bytes,
        filename: str,
        text: str | None = None,
    ) -> str:
        await self._throttle.acquire(_target(chat_id, user_id))
        try:
            with TemporaryDirectory(prefix="vremya-upload-") as directory:
                path = Path(directory) / Path(filename).name
                await asyncio.to_thread(path.write_bytes, data)
                media: list[Attachment | InputMedia | InputMediaBuffer | AttachmentUpload] = [
                    InputMedia(path=str(path), type=UploadType.FILE)
                ]
                sent = await self._bot.send_message(
                    chat_id=chat_id,
                    user_id=user_id,
                    text=text,
                    attachments=media,
                )
        except Exception as exc:
            raise translate(exc) from exc
        return _mid(sent)

    async def answer_callback(self, callback_id: str, *, notification: str) -> None:
        try:
            await self._bot.send_callback(callback_id=callback_id, notification=notification)
        except Exception as exc:
            raise translate(exc) from exc

    async def aclose(self) -> None:
        await self._bot.close_session()

def _mid(sent: Any) -> str:
    body = getattr(getattr(sent, "message", None), "body", None)
    mid = getattr(body, "mid", None)
    if not mid:
        raise MaxRetryableError(502, "empty_response")
    return str(mid)

@dataclass
class SentMessage:
    chat_id: int | None
    user_id: int | None
    text: str | None
    attachments: list[OutgoingAttachment] | None
    mid: str
    file: bytes | None = None
    filename: str | None = None

    def buttons(self) -> list[Any]:
        found: list[Any] = []
        for attachment in self.attachments or []:
            payload = getattr(attachment, "payload", None)
            for row in getattr(payload, "buttons", None) or []:
                found.extend(row)
        return found

@dataclass
class AnsweredCallback:
    callback_id: str
    notification: str

@dataclass
class FakeMaxTransport:

    sent: list[SentMessage] = field(default_factory=list)
    callbacks: list[AnsweredCallback] = field(default_factory=list)
    failures: list[BaseException] = field(default_factory=list)
    _next_mid: int = 0

    def _new_mid(self) -> str:
        if self.failures:
            raise self.failures.pop(0)
        self._next_mid += 1
        return f"fake-mid-{self._next_mid}"

    async def send_message(
        self,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        text: str,
        attachments: list[OutgoingAttachment] | None = None,
    ) -> str:
        _target(chat_id, user_id)
        mid = self._new_mid()
        self.sent.append(SentMessage(chat_id, user_id, text, attachments, mid))
        return mid

    async def send_file(
        self,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        data: bytes,
        filename: str,
        text: str | None = None,
    ) -> str:
        _target(chat_id, user_id)
        mid = self._new_mid()
        self.sent.append(SentMessage(chat_id, user_id, text, None, mid, data, filename))
        return mid

    async def answer_callback(self, callback_id: str, *, notification: str) -> None:
        self.callbacks.append(AnsweredCallback(callback_id, notification))

    @property
    def texts(self) -> list[str]:
        return [m.text or "" for m in self.sent]

    def to_chat(self, chat_id: int) -> list[SentMessage]:
        return [m for m in self.sent if m.chat_id == chat_id]

    def reset(self) -> None:
        self.sent.clear()
        self.callbacks.clear()
