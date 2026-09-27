import argparse
import asyncio
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from sqlalchemy import select

from app.clock import current_time
from app.config import get_settings
from app.db import session as db
from app.db.models import User
from app.seed import seed_by_mode, seed_demo


async def _seed_demo() -> int:
    async with db.transaction() as session:
        await seed_demo(session, current_time())
    print("Демо-данные загружены: X-Dev-User: 1 — Алина")
    return 0

async def _seed_auto() -> int:
    mode = os.environ.get("SEED_DEMO", "true")
    try:
        async with db.transaction() as session:
            done = await seed_by_mode(session, current_time(), mode)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        {
            "seeded": "Демо-данные загружены (первый запуск)",
            "refreshed": "Демо-данные обновлены (SEED_DEMO=refresh)",
            "skipped": f"Демо-данные не трогаем (SEED_DEMO={mode}"
            + (", демо уже есть)" if mode.strip().lower() == "true" else ")"),
        }[done]
    )
    return 0

async def _jobs_status() -> int:
    from app.worker.ops import backlog, status

    now = current_time()
    async with db.transaction() as session:
        rows = await status(session, now)
        found = await backlog(session, now)
    print(f"{'вид':<28}{'ждут':>7}{'повтор':>8}{'зависли':>9}{'исчерп.24ч':>12}")
    for row in rows:
        print(
            f"{row.kind:<28}{row.pending:>7}{row.failing:>8}{row.stuck:>9}{row.exhausted_24h:>12}"
        )
    if not rows:
        print("очередь пуста, исчерпанных за сутки нет")
    print(f"созрели сейчас: {found.due}; исчерпаны за час: {found.exhausted_last_hour}")
    stuck = sum(r.stuck + r.exhausted_24h for r in rows)
    if stuck:
        print("вернуть в очередь: python -m app.cli jobs-retry [--kind K] [--since ЧАСОВ]")
    return 0

async def _jobs_retry(kind: str | None, since_hours: float) -> int:
    from app.worker.ops import retry

    async with db.transaction() as session:
        count = await retry(session, current_time(), kind=kind, since_hours=since_hours)
    print(f"Возвращено в очередь: {count}")
    return 0

def _wait_https(base: str, timeout: float, interval: float = 5.0) -> bool:
    url = base.rstrip("/") + "/healthz"
    context = ssl.create_default_context()
    deadline = time.monotonic() + timeout
    last = ""
    while True:
        try:
            with urllib.request.urlopen(url, timeout=10, context=context) as response:  # noqa: S310
                if response.status == 200:
                    print(f"HTTPS готов: {url}")
                    return True
                last = f"HTTP {response.status}"
        except (urllib.error.URLError, OSError) as exc:
            last = type(getattr(exc, "reason", exc)).__name__
        if time.monotonic() >= deadline:
            print(f"HTTPS не готов за {int(timeout)} с ({url}: {last})", file=sys.stderr)
            return False
        print(f"Жду HTTPS ({last}), повтор через {int(interval)} с")
        time.sleep(interval)

async def _setup_webhook(wait: float) -> int:
    settings = get_settings()
    base = settings.public_base_url
    if not base.startswith("https://"):
        print("PUBLIC_BASE_URL не https — вебхук не подписан (локальный стенд)")
        return 0
    if not settings.max_bot_token:
        print("MAX_BOT_TOKEN пуст — вебхук не подписан", file=sys.stderr)
        return 1
    if not await asyncio.to_thread(_wait_https, base, wait):
        print(
            "Проверьте DNS, порты 80/443 и журнал Caddy (docker compose logs web), затем: "
            "docker compose up bot-setup",
            file=sys.stderr,
        )
        return 1
    code = await _set_webhook(base)
    if code != 0:
        return code
    return await _print_subscriptions()

async def _print_subscriptions() -> int:
    from maxapi import Bot

    bot = Bot(token=get_settings().max_bot_token, auto_requests=False)
    try:
        current = await bot.get_subscriptions()
    except Exception as exc:
        print(f"Не удалось прочитать подписки: {type(exc).__name__}", file=sys.stderr)
        return 1
    finally:
        await bot.close_session()
    for item in current.subscriptions:
        print(f"Подписка: {item.url}")
    return 0

async def _make_operator(max_user_id: int, revoke: bool) -> int:
    async with db.transaction() as session:
        user = await session.scalar(select(User).where(User.max_user_id == max_user_id))
        if user is None:
            print(f"Пользователь MAX {max_user_id} ещё не входил в приложение", file=sys.stderr)
            return 1
        user.is_operator = not revoke
    print(f"Оператор {'снят' if revoke else 'назначен'}: MAX {max_user_id}")
    return 0

async def _set_webhook(url: str) -> int:
    from app.bot.runtime import WEBHOOK_PATH, set_webhook
    from app.bot.transport import MaxApiError

    if not url.startswith("https://"):
        print("Нужен https:// адрес (порт 443, доверенный сертификат)", file=sys.stderr)
        return 1
    if not url.rstrip("/").endswith(WEBHOOK_PATH):
        url = url.rstrip("/") + WEBHOOK_PATH
    try:
        await set_webhook(url)
    except MaxApiError as exc:
        print(f"MAX отклонил подписку: {exc.status} {exc.code}", file=sys.stderr)
        return 1
    print(f"Webhook подписан: {url}")
    return 0

def _ensure_signing_cert(directory: str) -> int:
    from app.domain.pdf_signing import generate_self_signed

    folder = Path(directory)
    key, cert = folder / "sign.key", folder / "sign.crt"
    if key.exists() and cert.exists():
        print(f"Ключ подписи справок уже есть: {folder}")
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    key_pem, cert_pem = generate_self_signed("Время с пользой — справки о часах")
    key.write_bytes(key_pem)
    key.chmod(0o600)
    cert.write_bytes(cert_pem)
    print(f"Создан ключ подписи справок: {folder}")
    return 0

def _export_openapi(path: str) -> int:
    from app.main import app, export_openapi

    text = json.dumps(export_openapi(app), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    Path(path).write_text(text, encoding="utf-8")
    print(f"OpenAPI записан: {path}")
    return 0

async def _seed_calendar() -> int:
    from app.seed import demo_present
    from app.seed.rolling import CALENDAR_DAYS, seed_rolling

    async with db.transaction() as session:
        if not await demo_present(session):
            print("Сначала загрузи базовые демо-данные: python -m app.cli seed-demo")
            return 1
        await seed_rolling(session, current_time(), calendar_only=True)
    print(f"Афиша дополнена событиями на {CALENDAR_DAYS} дня; существующие события не изменены")
    return 0

async def _run(args: argparse.Namespace) -> int:
    try:
        if args.command == "seed-demo":
            return await _seed_demo()
        if args.command == "seed-calendar":
            return await _seed_calendar()
        if args.command == "seed-auto":
            return await _seed_auto()
        if args.command == "jobs-status":
            return await _jobs_status()
        if args.command == "jobs-retry":
            return await _jobs_retry(args.kind, args.since)
        if args.command == "setup-webhook":
            return await _setup_webhook(args.wait)
        if args.command == "set-webhook":
            return await _set_webhook(args.url)
        if args.command == "ensure-signing-cert":
            return _ensure_signing_cert(args.directory)
        if args.command == "export-openapi":
            return _export_openapi(args.path)
        if args.command == "make-operator":
            return await _make_operator(args.max_user_id, args.revoke)
        return 2
    finally:
        await db.dispose()

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed-demo", help="справочники, организации, демо-профиль Алины (MAX id 1)")
    sub.add_parser("seed-calendar", help="добавить демо-события на следующие три недели")
    sub.add_parser("seed-auto", help="демо после миграций по SEED_DEMO: true | refresh | false")
    sub.add_parser("jobs-status", help="очередь по видам: ждут, повторяются, исчерпаны")
    jr = sub.add_parser("jobs-retry", help="вернуть в очередь исчерпанные и зависшие задачи")
    jr.add_argument("--kind", help="только задачи этого вида (notify.instructions, …)")
    jr.add_argument("--since", type=float, default=24.0, help="исчерпанные за N часов (24)")
    sw = sub.add_parser("setup-webhook", help="дождаться HTTPS и подписать webhook (bot-setup)")
    sw.add_argument("--wait", type=float, default=300.0, help="ждать HTTPS до N секунд (300)")
    op = sub.add_parser("make-operator", help="выдать флаг оператора пользователю MAX")
    op.add_argument("max_user_id", type=int)
    op.add_argument("--revoke", action="store_true", help="снять флаг")
    sc = sub.add_parser("ensure-signing-cert", help="создать ключ подписи справок, если его нет")
    sc.add_argument("directory", nargs="?", default="/data/signing")
    ex = sub.add_parser("export-openapi", help="записать OpenAPI 3.1 в файл")
    ex.add_argument("path", nargs="?", default="../openapi/openapi.json")
    wh = sub.add_parser("set-webhook", help="подписать бота на POST /max/webhook")
    wh.add_argument("url", help="https://<домен> или полный адрес …/max/webhook")
    return asyncio.run(_run(parser.parse_args(argv)))

if __name__ == "__main__":
    sys.exit(main())
