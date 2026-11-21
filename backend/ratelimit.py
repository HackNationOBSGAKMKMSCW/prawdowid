"""Prosty limit żądań: przesuwane okno 60 s na adres IP klienta, w pamięci procesu.

Wystarcza na prototyp z jedną instancją. Przy wielu instancjach (np. serverless)
limit działa osobno w każdej z nich, wtedy trzeba przenieść stan do Redisa.

Konfiguracja:
- `RATE_LIMIT_PER_MINUTE` (domyślnie 10, 0 wyłącza limit)
- `TRUST_PROXY_HEADERS=1`: bierz IP z `X-Forwarded-For`. Włączaj tylko za zaufanym
  proxy, bo inaczej klient może podać dowolny adres i ominąć limit.
"""

import math
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

WINDOW_S = 60.0


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float = WINDOW_S, clock=time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> float:
        """Rejestruje żądanie. Zwraca 0, gdy wolno, albo liczbę sekund do odczekania."""
        if self.limit <= 0:
            return 0.0
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] + self.window_s - now
            hits.append(now)
            # Sprzątanie pustych kluczy, żeby słownik nie rósł bez końca.
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return 0.0


limiter = SlidingWindowLimiter(int(os.getenv("RATE_LIMIT_PER_MINUTE", "10")))


def client_key(request: Request) -> str:
    if os.getenv("TRUST_PROXY_HEADERS") == "1":
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """Zależność FastAPI: rzuca 429 po przekroczeniu limitu."""
    retry_after = limiter.hit(client_key(request))
    if retry_after > 0:
        raise HTTPException(
            status_code=429,
            detail="Za dużo zgłoszeń w krótkim czasie. Spróbuj ponownie za chwilę.",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )
