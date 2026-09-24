from collections.abc import Iterator

import pytest

from app.api.routers import certificate, deals


@pytest.fixture(autouse=True)
def _reset_throttles() -> Iterator[None]:
    deals.checkin_limiter.reset()
    certificate.check_limiter.reset()
    yield
