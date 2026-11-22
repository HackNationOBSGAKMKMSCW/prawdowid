"""Wątek roboczy panelu: zapisy do rejestru admina poza ścieżką obsługi żądania.

Żądanie HTTP tylko wrzuca zadanie do ograniczonej kolejki (``submit`` nie czeka i nie
blokuje pętli zdarzeń), a jeden wątek wykonuje zadania po kolei. Dzięki temu:

* skan SQL injection i zapis do bazy nie opóźniają odpowiedzi ani nie zajmują slotów
  ``check_semaphore`` i puli ``asyncio.to_thread``;
* zapisy alertów w jednym procesie idą sekwencyjnie (brak wyścigów licznika);
* zalew żądań (np. skaner podatności) nie zamienia się w zalew zapisów: gdy kolejka jest
  pełna, zadania są odrzucane i liczone w ``dropped``.

Błąd zadania jest logowany (tylko typ), nigdy nie wychodzi poza wątek.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_SIZE = 500


class BackgroundWorker:
    def __init__(self, name: str = "admin-worker", maxsize: int = DEFAULT_QUEUE_SIZE) -> None:
        self.name = name
        self._queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...]]] = queue.Queue(maxsize)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.dropped = 0

    def submit(self, fn: Callable[..., Any], *args: Any) -> bool:
        """Dodaj zadanie; ``False``, gdy kolejka jest pełna (zadanie odrzucone)."""
        self._ensure_thread()
        try:
            self._queue.put_nowait((fn, args))
        except queue.Full:
            self.dropped += 1
            if self.dropped == 1 or self.dropped % 100 == 0:
                logger.warning("admin_worker_queue_full worker=%s dropped=%d", self.name, self.dropped)
            return False
        return True

    def flush(self, timeout: float = 10.0) -> bool:
        """Poczekaj, aż kolejka się opróżni (testy, zamykanie aplikacji)."""
        done = threading.Event()

        def wait() -> None:
            self._queue.join()
            done.set()

        threading.Thread(target=wait, daemon=True).start()
        return done.wait(timeout)

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
                self._thread.start()

    def _run(self) -> None:
        while True:
            fn, args = self._queue.get()
            try:
                fn(*args)
            except Exception as exc:  # noqa: BLE001 - tylko typ błędu, bez danych
                logger.warning(
                    "admin_worker_task_failed worker=%s error_type=%s",
                    self.name,
                    type(exc).__name__,
                )
            finally:
                self._queue.task_done()
