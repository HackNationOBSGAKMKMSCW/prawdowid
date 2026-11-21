"""Per-request context shared by all instrumentation (works across asyncio.gather)."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestMetrics:
    """Mutable accumulator for one request; shared by every task spawned inside it."""

    request_id: str
    name: str
    started: float = field(default_factory=time.perf_counter)
    llm_calls: int = 0
    llm_errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    cost_unknown_calls: int = 0
    models: dict[str, int] = field(default_factory=dict)
    search_calls: int = 0
    search_errors: int = 0
    search_retries: int = 0
    injection_attempts: int = 0
    abstained: bool = False
    abstain_reasons: list[str] = field(default_factory=list)
    stages: dict[str, float] = field(default_factory=dict)
    reported_hashes: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, **increments: float) -> None:
        with self._lock:
            for name, value in increments.items():
                setattr(self, name, getattr(self, name) + value)

    def add_model(self, model: str) -> None:
        with self._lock:
            self.models[model] = self.models.get(model, 0) + 1

    def add_stage(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self.stages[name] = round(self.stages.get(name, 0.0) + duration_ms, 1)

    def mark_reported(self, digest: str) -> bool:
        """Return True the first time a digest is seen in this request."""
        with self._lock:
            if digest in self.reported_hashes:
                return False
            self.reported_hashes.add(digest)
            return True

    def abstain(self, reason: str) -> None:
        with self._lock:
            self.abstained = True
            if reason not in self.abstain_reasons:
                self.abstain_reasons.append(reason)

    def summary(self, *, ok: bool, error: str | None = None) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": round((time.perf_counter() - self.started) * 1000, 1),
            "ok": ok,
            "error": error,
            "llm_calls": self.llm_calls,
            "llm_errors": self.llm_errors,
            "models": dict(self.models),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "cost_complete": self.cost_unknown_calls == 0,
            "search_calls": self.search_calls,
            "search_errors": self.search_errors,
            "search_retries": self.search_retries,
            "injection_attempts": self.injection_attempts,
            "abstained": self.abstained,
            "abstain_reasons": list(self.abstain_reasons),
            "stages": dict(self.stages),
        }


_metrics: ContextVar[RequestMetrics | None] = ContextVar("obs_metrics", default=None)
_stage_stack: ContextVar[tuple[str, ...]] = ContextVar("obs_stage_stack", default=())


def current() -> RequestMetrics | None:
    return _metrics.get()


def current_request_id() -> str | None:
    metrics = _metrics.get()
    return metrics.request_id if metrics else None


def stage_stack() -> tuple[str, ...]:
    return _stage_stack.get()


@contextmanager
def push_stage(name: str) -> Iterator[None]:
    token = _stage_stack.set(_stage_stack.get() + (name,))
    try:
        yield
    finally:
        _stage_stack.reset(token)


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


@contextmanager
def request_scope(
    name: str = "request",
    *,
    request_id: str | None = None,
    emit_summary: bool = True,
) -> Iterator[RequestMetrics]:
    """Open a request context; on exit emits one ``request_summary`` event.

    Nested calls reuse the outer scope, so wrapping is always safe.
    """
    existing = _metrics.get()
    if existing is not None:
        yield existing
        return

    metrics = RequestMetrics(request_id=request_id or new_request_id(), name=name)
    token = _metrics.set(metrics)
    ok, error = True, None
    try:
        yield metrics
    except BaseException as exc:
        ok, error = False, type(exc).__name__
        raise
    finally:
        if emit_summary:
            from .events import log_event

            log_event("request_summary", **metrics.summary(ok=ok, error=error))
        _metrics.reset(token)
