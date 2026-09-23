import hashlib
import hmac
import json
from datetime import datetime
from urllib.parse import urlencode

BOT_TOKEN = "123456:test-bot-token"

def sign_init_data(user: dict[str, object], auth_date: datetime, *, token: str = BOT_TOKEN) -> str:
    fields = {
        "auth_date": str(int(auth_date.timestamp())),
        "user": json.dumps(user, ensure_ascii=False),
        "query_id": "q1",
    }
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)

def dev(user_or_max_id: object) -> dict[str, str]:
    max_id = getattr(user_or_max_id, "max_user_id", user_or_max_id)
    return {"X-Dev-User": str(max_id)}
