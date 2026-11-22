"""Small in-process TTL cache with stale-on-error and per-key request coalescing."""

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

_MAX_ENTRIES = 2000


class TTLCache:
    def __init__(self, max_entries: int = _MAX_ENTRIES) -> None:
        self._entries: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._key_locks: dict[Any, asyncio.Lock] = {}
        self._max_entries = max_entries

    def peek(self, key: Any) -> tuple[Any, bool] | None:
        """Return ``(value, is_fresh)`` or ``None`` when the key was never stored."""

        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        return value, expires_at > time.monotonic()

    def set(self, key: Any, value: Any, ttl: float) -> None:
        with self._lock:
            if key not in self._entries and len(self._entries) >= self._max_entries:
                self._entries.pop(next(iter(self._entries)))
            self._entries[key] = (time.monotonic() + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._key_locks.clear()

    async def get_or_fetch(
        self,
        key: Any,
        ttl: float,
        fetch: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Serve fresh values from cache; refresh once per key; fall back to stale on error."""

        cached = self.peek(key)
        if cached is not None and cached[1]:
            return cached[0]
        # asyncio locks bind to one event loop; key them by loop so separate asyncio.run calls work.
        lock_key = (id(asyncio.get_running_loop()), key)
        with self._lock:
            if len(self._key_locks) > self._max_entries:
                self._key_locks.clear()
            lock = self._key_locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            cached = self.peek(key)
            if cached is not None and cached[1]:
                return cached[0]
            try:
                value = await fetch()
            except Exception:
                if cached is not None:
                    return cached[0]
                raise
            if ttl > 0:
                self.set(key, value, ttl)
            return value


CACHE = TTLCache()
