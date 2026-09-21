from datetime import UTC, datetime


def current_time() -> datetime:
    return datetime.now(UTC)
