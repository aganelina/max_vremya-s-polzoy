import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from maxapi.connection.base import BaseConnection

from app.bot.transport import MaxapiTransport


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("vremya-export.json", b'{"profile": {}}'),
        ("certificate.pdf", b"%PDF-1.4\n"),
        ("attendance.csv", b"name,hours\nAlina,2\n"),
        ("unknown.custom", b"1234"),
    ],
)
async def test_multipart_preserves_exact_filename(name, data, monkeypatch):
    captured = []
    paths = []

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def text(self):
            return "{}"

    class Session:
        closed = False

        def post(self, *, url, data):
            captured.append(data._fields[0][0]["filename"])
            return Response()

    connection = BaseConnection()
    monkeypatch.setattr(BaseConnection, "_ensure_bot", lambda _: SimpleNamespace(session=Session()))

    async def send_message(**kwargs):
        [media] = kwargs["attachments"]
        paths.append(media.path)
        assert await asyncio.to_thread(Path(media.path).read_bytes) == data
        await connection.upload_file("https://upload.invalid", media.path, media.type)
        return SimpleNamespace(message=SimpleNamespace(body=SimpleNamespace(mid="test-mid")))

    transport = MaxapiTransport(
        SimpleNamespace(send_message=send_message), throttle=SimpleNamespace(acquire=AsyncMock())
    )
    assert await transport.send_file(chat_id=1, data=data, filename=name) == "test-mid"
    assert captured == [name]
    assert not await asyncio.to_thread(Path(paths[0]).exists)
