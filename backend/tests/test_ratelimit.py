from fastapi.testclient import TestClient

import ratelimit
from main import app
from ratelimit import SlidingWindowLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limiter_blocks_after_limit_and_frees_after_window():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=2, window_s=60, clock=clock)
    assert limiter.hit("a") == 0
    assert limiter.hit("a") == 0
    assert limiter.hit("a") == 60  # trzeba czekać do wygaśnięcia pierwszego żądania
    assert limiter.hit("b") == 0  # inny klient ma osobny licznik
    clock.now += 60
    assert limiter.hit("a") == 0


def test_zero_limit_disables_limiting():
    limiter = SlidingWindowLimiter(limit=0)
    assert all(limiter.hit("a") == 0 for _ in range(100))


def test_check_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(ratelimit, "limiter", SlidingWindowLimiter(limit=2))
    client = TestClient(app)
    payload = {"input": "Czy paszport można odebrać w jeden dzień?"}
    assert client.post("/api/check", json=payload).status_code == 200
    assert client.post("/api/check", json=payload).status_code == 200
    r = client.post("/api/check", json=payload)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    assert r.json()["error"]["code"] == "rate_limited"


def test_forwarded_for_used_only_when_trusted(monkeypatch):
    monkeypatch.setattr(ratelimit, "limiter", SlidingWindowLimiter(limit=1))
    client = TestClient(app)
    payload = {"input": "Czy paszport można odebrać w jeden dzień?"}

    # Bez zaufanego proxy nagłówek jest ignorowany: zmiana IP nie omija limitu.
    assert (
        client.post("/api/check", json=payload, headers={"x-forwarded-for": "1.1.1.1"}).status_code
        == 200
    )
    assert (
        client.post("/api/check", json=payload, headers={"x-forwarded-for": "2.2.2.2"}).status_code
        == 429
    )

    monkeypatch.setenv("TRUST_PROXY_HEADERS", "1")
    assert (
        client.post("/api/check", json=payload, headers={"x-forwarded-for": "3.3.3.3"}).status_code
        == 200
    )
