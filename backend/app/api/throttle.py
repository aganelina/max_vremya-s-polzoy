import time
from collections import deque
from threading import Lock

from app.api.errors import ApiError


class RateLimited(ApiError):
    def __init__(self) -> None:
        super().__init__(429, "rate_limited")

class SlidingWindow:
    def __init__(self, limit: int, period_s: float = 60.0) -> None:
        self.limit = limit
        self.period = period_s
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= t - self.period:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(t)
            if len(self._hits) > 50_000:
                self._hits = {k: v for k, v in self._hits.items() if v}
            return True

    def hit(self, key: str) -> None:
        if not self.allow(key):
            raise RateLimited()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

user_limiter = SlidingWindow(20, period_s=1.0)
sensitive_limiter = SlidingWindow(5)

def reset_all() -> None:
    user_limiter.reset()
    sensitive_limiter.reset()
