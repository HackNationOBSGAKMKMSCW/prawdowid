"""Limit sprawdzeń na adres klienta i wspólna bramka strony i WhatsAppa."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from request_limits import CheckGate, RateLimiter, parse_rate_limits
from server import create_app
from test_browser_api import FakeStore, report


def test_parse_rate_limits():
    assert parse_rate_limits("6/minute, 60/hours") == [(6, 60.0), (60, 3600.0)]
    assert parse_rate_limits("off") == [] and parse_rate_limits("") == []
    with pytest.raises(ValueError):
        parse_rate_limits("6 per minute")


def test_sliding_window_per_key():
    now = [0.0]
    limiter = RateLimiter([(2, 60.0), (3, 3600.0)], clock=lambda: now[0])
    assert limiter.hit("a") is None and limiter.hit("a") is None
    assert limiter.hit("a") == pytest.approx(60.0)  # trzecie w minucie: czekaj
    assert limiter.hit("b") is None  # inny klient ma własny limit
    now[0] = 61.0
    assert limiter.hit("a") is None  # okno minuty minęło
    now[0] = 62.0
    assert limiter.hit("a") == pytest.approx(3600.0 - 62.0)  # limit godzinowy
    assert limiter.hit("a") == pytest.approx(3600.0 - 62.0)  # odmowa nie zużywa limitu


def test_limiter_keeps_memory_bounded():
    now = [0.0]
    limiter = RateLimiter([(1, 10.0)], clock=lambda: now[0], max_keys=3)
    for key in "abc":
        limiter.hit(key)
    now[0] = 20.0
    limiter.hit("d")
    assert set(limiter._hits) == {"d"}  # stare klucze usunięte


async def test_gate_slots():
    gate = CheckGate(asyncio.Semaphore(1))
    assert await gate.try_acquire() and gate.busy()
    assert not await gate.try_acquire()
    gate.release()
    assert not gate.busy()


def payload(text: str) -> dict:
    message = {"from": "48500", "id": "w1", "type": "text", "text": {"body": text}}
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"field": "messages", "value": {"messages": [message]}}]}],
    }


def test_check_is_rate_limited_per_address_on_web_and_whatsapp(monkeypatch):
    monkeypatch.setenv("SPRAWDZTO_MODE", "demo")
    monkeypatch.setenv("ADMIN_MONITOR", "off")

    async def runner(text: str) -> dict:
        return report()

    app = create_app(
        store=FakeStore(),
        verification_runner=runner,
        admin_panel=False,
        rate_limiter=RateLimiter([(2, 60.0)]),
    )
    with TestClient(app) as client:
        for _ in range(2):
            assert client.get("/api/check", params={"text": "Szczepionki to trucizna."}).status_code == 200
        limited = client.get("/api/check", params={"text": "Szczepionki to trucizna."})
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert 1 <= int(limited.headers["Retry-After"]) <= 60
        # ten sam adres przez WhatsApp: limit wspólny, odpowiedź w czacie
        reply = client.post("/api/whatsapp/webhook", json=payload("Szczepionki to trucizna."))
        (message,) = reply.json()["messages"]
        assert "Wysyłasz dużo wiadomości" in message["text"]["body"]
