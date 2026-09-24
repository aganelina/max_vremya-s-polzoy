import secrets

from app.config import get_settings

DEFAULT_BOT = "vremya_bot"

def new_token() -> str:
    return secrets.token_urlsafe(16)

def startapp_link(prefix: str, token: str) -> str:
    bot = get_settings().max_bot_username or DEFAULT_BOT
    return f"https://max.ru/{bot}?startapp={prefix}_{token}"
