import pytest

import ratelimit


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    """Każdy test dostaje własny limiter, żeby testy nie zjadały sobie limitu."""
    monkeypatch.setattr(ratelimit, "limiter", ratelimit.SlidingWindowLimiter(limit=1000))
