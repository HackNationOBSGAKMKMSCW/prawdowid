"""Adres klienta do blokad po prompt injection: bez podszywania się przez nagłówki."""

from __future__ import annotations

from admin.client_ip import client_address, identity


def test_cloudflare_header_wins_and_cannot_be_overridden_by_forwarded_for():
    headers = {
        b"cf-connecting-ip": b"203.0.113.7",
        b"x-forwarded-for": b"198.51.100.9, 104.16.0.1",
    }
    assert client_address(headers, "10.0.0.2", header="cf-connecting-ip") == "203.0.113.7"


def test_forwarded_for_uses_the_address_appended_by_the_trusted_proxy():
    # klient wpisał 198.51.100.9 na początek listy; proxy dopisało jego prawdziwy adres
    headers = {b"x-forwarded-for": b"198.51.100.9, 203.0.113.7"}
    assert client_address(headers, "10.0.0.2", header="", hops=1) == "203.0.113.7"
    assert client_address(headers, "10.0.0.2", header="", hops=2) == "198.51.100.9"
    # bez zaufanych proxy nagłówki są ignorowane
    assert client_address(headers, "10.0.0.2", header="", hops=0) == "10.0.0.2"


def test_invalid_values_fall_back_to_the_connection_address():
    headers = {b"cf-connecting-ip": b"nie-adres", b"x-forwarded-for": b"unknown"}
    assert client_address(headers, "203.0.113.7", header="cf-connecting-ip", hops=1) == (
        "203.0.113.7"
    )
    assert client_address({}, "testclient", header="", hops=1) is None
    assert client_address({}, "[2001:db8::1]:443", header="", hops=0) == "2001:db8::1"
    assert client_address({}, "::ffff:203.0.113.7", header="", hops=0) == "203.0.113.7"


def test_identity_is_a_keyed_hash_with_a_mask():
    first = identity("203.0.113.7", "sol-a")
    assert first.label == "203.0.113.x" and len(first.key) == 32
    assert "203" not in first.key
    assert identity("203.0.113.7", "sol-a") == first
    assert identity("203.0.113.7", "sol-b").key != first.key  # bez soli nie da się odtworzyć
    assert identity("203.0.113.8", "sol-a").key != first.key
    v6 = identity("2001:db8:1:2::10", "sol-a")
    assert v6 == identity("2001:db8:1:2:ffff::1", "sol-a")  # ta sama sieć /64
    assert v6.label == "2001:db8:1:…/64"
    assert identity("nie-adres", "sol-a") is None
