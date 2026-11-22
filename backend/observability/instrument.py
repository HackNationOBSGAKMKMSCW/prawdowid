"""Runtime auto-instrumentation: wraps existing functions without editing their files.

Every patch is independent and fail-safe: a missing module, a renamed function or any
error while patching is recorded in ``status()`` and skipped; the application keeps
working. ``revert_all()`` restores the originals.

To instrument new code without touching this file, set e.g.
``LOG_TRACE_TARGETS="articleScraping.service:run=scraping.run,pkg.mod:Class.method"``
or call ``register_stage(...)`` before ``init()``.
"""

from __future__ import annotations

import contextlib
import functools
import importlib
import inspect
import logging
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any

from .context import current, stage_stack
from .events import log_abstain, log_event, log_prompt_injection
from .injection import scan
from .pricing import estimate_cost
from .tracing import wrap_stage

logger = logging.getLogger(__name__)
_MISSING = object()


@dataclass
class _Patch:
    owner: Any
    attr: str
    original: Any  # raw value from owner.__dict__ (or _MISSING when inherited)


_applied: list[_Patch] = []
_status: dict[str, str] = {}


def status() -> dict[str, str]:
    """Which patches were applied or skipped (and why)."""
    return dict(_status)


def _set(owner: Any, attr: str, value: Any) -> None:
    original = vars(owner).get(attr, _MISSING)
    setattr(owner, attr, value)
    _applied.append(_Patch(owner, attr, original))


def revert_all() -> None:
    while _applied:
        patch = _applied.pop()
        with contextlib.suppress(Exception):
            if patch.original is _MISSING:
                delattr(patch.owner, patch.attr)
            else:
                setattr(patch.owner, patch.attr, patch.original)
    _status.clear()


def _resolve(module_name: str, path: str) -> tuple[ModuleType, Any, str, Any]:
    """Return (module, owner, attr, current value) for ``Class.method`` or ``func``."""
    module = importlib.import_module(module_name)
    owner: Any = module
    *parents, attr = path.split(".")
    for part in parents:
        owner = getattr(owner, part)
    return module, owner, attr, getattr(owner, attr)


def _is_wrapped(value: Any) -> bool:
    raw = getattr(value, "__func__", value)
    return bool(getattr(raw, "__obs_wrapped__", False))


def _replace_reexports(original: Any, replacement: Any, attr: str, skip: Any) -> None:
    """Also swap ``from x import f`` copies already bound in other loaded modules."""
    for module in list(sys.modules.values()):
        if module is None or module is skip:
            continue
        try:
            if vars(module).get(attr) is original:
                _set(module, attr, replacement)
        except Exception:  # noqa: BLE001
            continue


def _guarded(key: str, func: Callable[[], None]) -> None:
    if key in _status and _status[key] == "applied":
        return
    try:
        func()
        _status[key] = "applied"
    except Exception as exc:  # noqa: BLE001 - instrumentation is best effort
        _status[key] = f"skipped: {type(exc).__name__}: {exc}"[:200]
        logger.debug("instrumentation skipped: %s (%s)", key, exc)


# --------------------------------------------------------------------------- stages


@dataclass(frozen=True)
class StageTarget:
    module: str
    path: str
    name: str
    on_call: Callable[[tuple, dict], None] | None = None
    on_result: Callable[[Any], None] | None = None


def patch_stage(target: StageTarget) -> None:
    module, owner, attr, value = _resolve(target.module, target.path)
    if _is_wrapped(value):
        return
    if isinstance(vars(owner).get(attr), staticmethod | classmethod):
        raise TypeError("static/class methods are not supported as stage targets")
    wrapped = wrap_stage(value, target.name, on_call=target.on_call, on_result=target.on_result)
    _set(owner, attr, wrapped)
    if owner is module:
        _replace_reexports(value, wrapped, attr, skip=module)


def patch_result_hook(module_name: str, path: str, hook: Callable[[Any], None]) -> None:
    """Call ``hook(result)`` after a sync/async function, without timing it as a stage."""
    module, owner, attr, value = _resolve(module_name, path)
    if _is_wrapped(value):
        return

    if inspect.iscoroutinefunction(value):

        @functools.wraps(value)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await value(*args, **kwargs)
            _call_hook(hook, result)
            return result

    else:

        @functools.wraps(value)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = value(*args, **kwargs)
            _call_hook(hook, result)
            return result

    wrapper.__obs_wrapped__ = True  # type: ignore[attr-defined]
    _set(owner, attr, wrapper)
    if owner is module:
        _replace_reexports(value, wrapper, attr, skip=module)


def _call_hook(hook: Callable[[Any], None], value: Any) -> None:
    with contextlib.suppress(Exception):
        hook(value)


_extra_targets: list[StageTarget] = []


def register_stage(module: str, path: str, name: str | None = None, **hooks: Any) -> None:
    """Add a stage target (applied on next ``init()``/``apply_all()``)."""
    _extra_targets.append(StageTarget(module, path, name or f"{module}.{path}", **hooks))


def _env_targets() -> list[StageTarget]:
    targets = []
    for item in filter(None, (s.strip() for s in os.getenv("LOG_TRACE_TARGETS", "").split(","))):
        spec, _, name = item.partition("=")
        module, _, path = spec.partition(":")
        if module and path:
            targets.append(StageTarget(module, path, name or f"{module}.{path}"))
    return targets


# --------------------------------------------------------------------------- LLM


def _usage_numbers(response: Any) -> tuple[int | None, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None, None
    prompt = getattr(usage, "prompt_tokens", None)
    if prompt is None:
        prompt = getattr(usage, "input_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if completion is None:
        completion = getattr(usage, "output_tokens", None)
    return prompt, completion


def _finish_reason(response: Any) -> str | None:
    choices = getattr(response, "choices", None)
    if choices:
        return getattr(choices[0], "finish_reason", None)
    return getattr(response, "status", None)


def record_llm_call(
    *,
    api: str,
    kwargs: dict[str, Any],
    started: float,
    response: Any = None,
    error: BaseException | None = None,
) -> None:
    """Log one LLM call and add its tokens/cost to the current request."""
    requested_model = kwargs.get("model")
    model = getattr(response, "model", None) or requested_model
    streamed = bool(kwargs.get("stream"))
    prompt, completion = (None, None) if streamed else _usage_numbers(response)
    cost = None
    if prompt is not None and completion is not None:
        cost = estimate_cost(model, prompt, completion)
        if cost is None and model != requested_model:
            cost = estimate_cost(requested_model, prompt, completion)
    response_format = kwargs.get("response_format")

    metrics = current()
    if metrics is not None:
        metrics.add(llm_calls=1)
        metrics.add_model(str(model))
        if error is not None:
            metrics.add(llm_errors=1)
        if prompt is not None:
            metrics.add(prompt_tokens=prompt, completion_tokens=completion or 0)
        if cost is not None:
            metrics.add(cost_usd=cost)
        elif error is None:
            metrics.add(cost_unknown_calls=1)

    log_event(
        "llm_call",
        level="warning" if error is not None else "info",
        api=api,
        model=model,
        requested_model=requested_model if requested_model != model else None,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=(prompt or 0) + (completion or 0) if prompt is not None else None,
        cost_usd=cost,
        ok=error is None,
        error=type(error).__name__ if error is not None else None,
        status_code=getattr(error, "status_code", None),
        finish_reason=None if error is not None or streamed else _finish_reason(response),
        response_format=response_format.get("type")
        if isinstance(response_format, dict)
        else (getattr(response_format, "__name__", None) if response_format else None),
        streamed=streamed or None,
    )


def _wrap_llm_method(func: Callable[..., Any], api: str) -> Callable[..., Any]:
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            started = time.perf_counter()
            try:
                response = await func(self, *args, **kwargs)
            except Exception as exc:
                record_llm_call(api=api, kwargs=kwargs, started=started, error=exc)
                raise
            record_llm_call(api=api, kwargs=kwargs, started=started, response=response)
            return response

        async_wrapper.__obs_wrapped__ = True  # type: ignore[attr-defined]
        return async_wrapper

    async def _await_and_record(awaitable: Any, kwargs: dict[str, Any], started: float) -> Any:
        try:
            response = await awaitable
        except Exception as exc:
            record_llm_call(api=api, kwargs=kwargs, started=started, error=exc)
            raise
        record_llm_call(api=api, kwargs=kwargs, started=started, response=response)
        return response

    @functools.wraps(func)
    def sync_wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        # Some SDK versions expose async methods as plain functions returning a coroutine.
        started = time.perf_counter()
        try:
            response = func(self, *args, **kwargs)
        except Exception as exc:
            record_llm_call(api=api, kwargs=kwargs, started=started, error=exc)
            raise
        if inspect.isawaitable(response):
            return _await_and_record(response, kwargs, started)
        record_llm_call(api=api, kwargs=kwargs, started=started, response=response)
        return response

    sync_wrapper.__obs_wrapped__ = True  # type: ignore[attr-defined]
    return sync_wrapper


_LLM_TARGETS = (
    ("openai.resources.chat.completions", "AsyncCompletions", ("create", "parse"), "chat"),
    ("openai.resources.chat.completions", "Completions", ("create", "parse"), "chat"),
    ("openai.resources.responses", "AsyncResponses", ("create", "parse"), "responses"),
    ("openai.resources.responses", "Responses", ("create", "parse"), "responses"),
)


def _patch_openai() -> None:
    found = False
    for module_name, class_name, methods, api in _LLM_TARGETS:
        try:
            cls = getattr(importlib.import_module(module_name), class_name)
        except (ImportError, AttributeError):
            continue
        for method in methods:
            func = vars(cls).get(method)
            if func is None or not callable(func):
                continue
            found = True
            if not _is_wrapped(func):
                _set(cls, method, _wrap_llm_method(func, f"{api}.{method}"))
    if not found:
        raise RuntimeError("no OpenAI SDK methods found to patch")


# --------------------------------------------------------------------------- search APIs


def _provider(client: Any) -> dict[str, Any]:
    from urllib.parse import urlparse

    return {
        "provider": getattr(client, "name", type(client).__name__),
        "host": urlparse(str(getattr(client, "base_url", ""))).netloc or None,
    }


def _patch_search_client() -> None:
    from apiReading.base import BaseApiClient  # type: ignore[import-not-found]

    request = vars(BaseApiClient)["_request"]
    if not _is_wrapped(request):

        @functools.wraps(request)
        async def _request(self: Any, spec: Any) -> Any:
            started = time.perf_counter()
            metrics = current()
            if metrics is not None:
                metrics.add(search_calls=1)
            try:
                response = await request(self, spec)
            except Exception as exc:
                if metrics is not None:
                    metrics.add(search_errors=1)
                # Only type/status: exception messages may carry credential-bearing URLs.
                log_event(
                    "search_error",
                    level="warning",
                    **_provider(self),
                    method=getattr(spec, "method", None),
                    latency_ms=round((time.perf_counter() - started) * 1000, 1),
                    error=type(exc).__name__,
                    status_code=getattr(exc, "status_code", None),
                    retry_after=getattr(exc, "retry_after", None),
                )
                raise
            log_event(
                "search_call",
                **_provider(self),
                method=getattr(spec, "method", None),
                status_code=getattr(response, "status_code", None),
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            return response

        _request.__obs_wrapped__ = True  # type: ignore[attr-defined]
        _set(BaseApiClient, "_request", _request)

    sleep = vars(BaseApiClient).get("_sleep_before_retry")
    if sleep is not None and not _is_wrapped(sleep):

        @functools.wraps(sleep)
        async def _sleep_before_retry(self: Any, attempt: int, *args: Any, **kwargs: Any) -> Any:
            metrics = current()
            if metrics is not None:
                metrics.add(search_retries=1)
            log_event(
                "search_retry",
                level="warning",
                **_provider(self),
                attempt=attempt + 1,
                reason=kwargs.get("reason"),
                retry_after=args[0] if args else kwargs.get("retry_after"),
            )
            return await sleep(self, attempt, *args, **kwargs)

        _sleep_before_retry.__obs_wrapped__ = True  # type: ignore[attr-defined]
        _set(BaseApiClient, "_sleep_before_retry", _sleep_before_retry)


# --------------------------------------------------------------------------- prompt injection

_PATTERN_IN_WARNING = re.compile(r"'(.+)'")


def _text_source() -> str:
    return "url" if any("url" in name.lower() for name in stage_stack()) else "text"


def _inspect_sanitizer(raw_text: Any, result: Any) -> None:
    if not isinstance(raw_text, str) or not isinstance(result, tuple) or len(result) != 2:
        return
    warnings = result[1] or []
    source = _text_source()
    found = False
    for warning in warnings:
        text = str(warning)
        if "przycięty" in text or "truncated" in text.lower():
            log_event("input_truncated", source=source, text_length=len(raw_text))
        elif "wzorzec" in text or "manipulac" in text or "injection" in text.lower():
            found = True
            match = _PATTERN_IN_WARNING.search(text)
            hit = scan(raw_text)
            log_prompt_injection(
                text=raw_text,
                pattern=match.group(1) if match else text[:120],
                source=source,
                kind="input_pattern",
                snippet=hit.snippet if hit else None,
                detector="InputSanitizer",
            )
    if not found:  # second opinion: our broader pattern list
        hit = scan(raw_text)
        if hit is not None:
            log_prompt_injection(
                text=raw_text,
                pattern=hit.pattern,
                source=source,
                kind="input_pattern",
                snippet=hit.snippet,
                detector="observability",
            )


def _patch_input_sanitizer() -> None:
    from textAnalysis.analysis import InputSanitizer  # type: ignore[import-not-found]

    raw = vars(InputSanitizer)["sanitize"]
    func = raw.__func__ if isinstance(raw, classmethod) else raw
    if _is_wrapped(func):
        return

    @functools.wraps(func)
    def sanitize(cls: Any, raw_text: Any, *args: Any, **kwargs: Any) -> Any:
        result = func(cls, raw_text, *args, **kwargs)
        with contextlib.suppress(Exception):
            _inspect_sanitizer(raw_text, result)
        return result

    sanitize.__obs_wrapped__ = True  # type: ignore[attr-defined]
    _set(
        InputSanitizer,
        "sanitize",
        classmethod(sanitize) if isinstance(raw, classmethod) else sanitize,
    )


def _inspect_output_warnings(parsed: Any, new_warnings: list[str]) -> None:
    reasoning = str(getattr(parsed, "context_reasoning", "") or "")
    for warning in new_warnings:
        text = str(warning).lower()
        if "canary" in text or "wyciek" in text:
            log_prompt_injection(
                text=reasoning or warning,
                pattern="system_canary_in_output",
                source="llm_output",
                kind="system_prompt_leak",
            )
            log_abstain("blocked_security", detail="system_prompt_leak")
        elif "kategori" in text:
            log_prompt_injection(
                text=f"category:{getattr(parsed, 'category', '')}",
                pattern="category_outside_allowed_list",
                source="llm_output",
                kind="output_hijack_suspected",
                snippet=str(getattr(parsed, "category", ""))[:80],
            )


def _patch_output_security() -> None:
    from textAnalysis.analysis import ProxyContextAnalyzer  # type: ignore[import-not-found]

    func = vars(ProxyContextAnalyzer)["_validate_output_security"]
    if _is_wrapped(func):
        return

    @functools.wraps(func)
    def _validate_output_security(self: Any, parsed: Any, warnings: list[str]) -> Any:
        before = len(warnings)
        result = func(self, parsed, warnings)
        with contextlib.suppress(Exception):
            _inspect_output_warnings(parsed, list(warnings[before:]))
        return result

    _validate_output_security.__obs_wrapped__ = True  # type: ignore[attr-defined]
    _set(ProxyContextAnalyzer, "_validate_output_security", _validate_output_security)


def _scan_input_data_call(args: tuple, kwargs: dict) -> None:
    """inputDataAnalysis.analyze_async(user_input, sources, ...): direct + indirect injection."""
    user_input = kwargs.get("user_input", args[0] if args else None)
    if isinstance(user_input, str):
        hit = scan(user_input)
        if hit is not None:
            log_prompt_injection(
                text=user_input,
                pattern=hit.pattern,
                source="text",
                snippet=hit.snippet,
                detector="observability",
            )
    sources = kwargs.get("sources", args[1] if len(args) > 1 else None) or []
    for source in list(sources)[:50]:
        content = (
            source.get("content") if isinstance(source, dict) else getattr(source, "content", None)
        )
        source_id = source.get("id") if isinstance(source, dict) else getattr(source, "id", None)
        if isinstance(content, str):
            hit = scan(content)
            if hit is not None:
                log_prompt_injection(
                    text=content,
                    pattern=hit.pattern,
                    source=f"truth_source:{source_id}",
                    kind="indirect_source",
                    snippet=hit.snippet,
                    detector="observability",
                )


# --------------------------------------------------------------------------- abstain / evidence


def _evidence_from_reading(results: Any) -> None:
    items = list(results) if isinstance(results, list | tuple) else [results]
    total_items = sum(len(getattr(r, "items", []) or []) for r in items)
    outcomes = [o for r in items for o in (getattr(r, "results", []) or [])]
    failed = sum(1 for o in outcomes if getattr(o, "error", None) is not None)
    if total_items == 0:
        log_event(
            "evidence_empty",
            level="warning",
            queries=len(items),
            outcomes=len(outcomes),
            failed_outcomes=failed,
            reason="search_failed" if outcomes and failed == len(outcomes) else "no_results",
        )


def _evidence_from_trusted(report: Any) -> None:
    hits = getattr(report, "hits", None)
    if hits is None:
        return
    failures = getattr(report, "failures", []) or []
    queried = getattr(report, "sources_queried", 0) or 0
    log_event(
        "trusted_search",
        hits=len(hits),
        articles=sum(1 for hit in hits if getattr(hit, "kind", "") == "article"),
        sources_queried=queried,
        failed_sources=len(failures),
        duration_ms=getattr(report, "duration_ms", None),
    )
    if not hits:
        log_event(
            "evidence_empty",
            level="warning",
            provider="trusted_sources",
            reason="search_failed" if queried and len(failures) >= queried else "no_results",
        )


def _abstain_from_verdict(verdict: Any) -> None:
    value = str(getattr(verdict, "value", verdict))
    if value in {"no_data", "unverified"}:
        log_abstain(f"verdict_{value}")


# --------------------------------------------------------------------------- registry

STAGE_TARGETS: tuple[StageTarget, ...] = (
    StageTarget("textAnalysis.analysis", "run", "textAnalysis.run"),
    StageTarget("textAnalysis.analysis", "run_url", "textAnalysis.run_url"),
    StageTarget("textAnalysis.analysis", "ProxyContextAnalyzer.analyze", "textAnalysis.analyze"),
    StageTarget(
        "textAnalysis.analysis", "ProxyContextAnalyzer.analyze_url", "textAnalysis.analyze_url"
    ),
    StageTarget("textAnalysis.analysis", "UrlContentFetcher.fetch_text", "textAnalysis.fetch_url"),
    StageTarget("apiReading.reading", "run", "apiReading.run", on_result=_evidence_from_reading),
    StageTarget(
        "apiReading.full_text",
        "run_full_text",
        "apiReading.run_full_text",
        on_result=_evidence_from_reading,
    ),
    StageTarget("articleScraping.service", "run", "articleScraping.run"),
    StageTarget(
        "trustedSources.service", "run", "trustedSources.run", on_result=_evidence_from_trusted
    ),
    StageTarget(
        "inputDataAnalysis.pipeline",
        "analyze_async",
        "inputDataAnalysis.analyze",
        on_call=_scan_input_data_call,
    ),
    StageTarget("whatsappAdapter.pipeline", "LivePipeline.check", "whatsapp.check"),
    StageTarget("whatsappAdapter.pipeline", "DemoPipeline.check", "whatsapp.check_demo"),
)

_SPECIAL: tuple[tuple[str, Callable[[], None]], ...] = (
    ("llm:openai", _patch_openai),
    ("search:apiReading.BaseApiClient", _patch_search_client),
    ("injection:textAnalysis.InputSanitizer", _patch_input_sanitizer),
    ("injection:textAnalysis.output_security", _patch_output_security),
    (
        "abstain:whatsappAdapter.overall_verdict",
        lambda: patch_result_hook(
            "whatsappAdapter.verdicts", "overall_verdict", _abstain_from_verdict
        ),
    ),
)


def apply_all() -> dict[str, str]:
    """Apply every known patch; returns the status map."""
    for key, func in _SPECIAL:
        _guarded(key, func)
    for target in (*STAGE_TARGETS, *_extra_targets, *_env_targets()):
        _guarded(f"stage:{target.module}:{target.path}", lambda t=target: patch_stage(t))
    applied = sorted(k for k, v in _status.items() if v == "applied")
    skipped = sorted(k for k, v in _status.items() if v != "applied")
    log_event("instrumentation", applied=applied, skipped=skipped)
    return status()
