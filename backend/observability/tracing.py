"""Stage timing: ``@traced`` decorator and ``stage()`` context manager (sync + async)."""

from __future__ import annotations

import contextlib
import functools
import inspect
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from typing import Any, TypeVar

from .context import current, push_stage, request_scope
from .events import log_event

F = TypeVar("F", bound=Callable[..., Any])
ResultHook = Callable[[Any], None]


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Time a block. Outside any request it opens one (so CLI runs also get a summary)."""
    scope = request_scope(name) if current() is None else nullcontext()
    with scope:
        started = time.perf_counter()
        ok, error = True, None
        try:
            with push_stage(name):
                yield
        except BaseException as exc:
            ok, error = False, type(exc).__name__
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            metrics = current()
            if metrics is not None:
                metrics.add_stage(name, duration_ms)
            log_event(
                "stage",
                level="info" if ok else "warning",
                stage_name=name,
                duration_ms=duration_ms,
                ok=ok,
                error=error,
            )


def _safe(hook: ResultHook | None, value: Any) -> None:
    if hook is None:
        return
    with contextlib.suppress(Exception):
        hook(value)


def wrap_stage(
    func: F,
    name: str,
    *,
    on_call: Callable[[tuple, dict], None] | None = None,
    on_result: ResultHook | None = None,
) -> F:
    """Wrap a function (sync or async) in ``stage(name)`` with optional hooks."""

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            with stage(name):
                if on_call is not None:
                    _safe(lambda _: on_call(args, kwargs), None)
                result = await func(*args, **kwargs)
                _safe(on_result, result)
                return result

        async_wrapper.__obs_wrapped__ = True  # type: ignore[attr-defined]
        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        with stage(name):
            if on_call is not None:
                _safe(lambda _: on_call(args, kwargs), None)
            result = func(*args, **kwargs)
            _safe(on_result, result)
            return result

    sync_wrapper.__obs_wrapped__ = True  # type: ignore[attr-defined]
    return sync_wrapper  # type: ignore[return-value]


def traced(name: str | None = None) -> Callable[[F], F]:
    """Decorator for new code: ``@traced("myModule.step")``."""

    def decorator(func: F) -> F:
        return wrap_stage(func, name or f"{func.__module__}.{func.__qualname__}")

    return decorator
