"""In-memory whitelist of trusted sources, loaded from a ``SourceStore``.

The list itself is read-only here: it comes from the hardcoded ``whitelist.py``
today and from a PostgreSQL table later (see ``store.py``). The registry only
keeps what detection learns at runtime (adapter type, parameters, last check),
keyed by URL, so it survives reloads of the list.
"""

import logging
import re
import threading
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from articleScraping.url_validation import InvalidUrlError, validate_url
from pydantic import ValidationError

from .adapters.fact_check import KNOWN_PUBLISHERS
from .adapters.govpl import is_govpl_url, site_id_from_url
from .models import PENDING_ADAPTER, TrustedSource
from .store import SourceStore, StaticSourceStore

logger = logging.getLogger(__name__)

_ID_CHARS = re.compile(r"[^a-z0-9]+")
_DETECTED_FIELDS = ("adapter", "params", "last_check", "description")
# Sejm's ELI API serves the acts; ISAP is the public catalogue linking to the same acts.
SEJM_ELI_HOSTS = frozenset({"api.sejm.gov.pl", "isap.sejm.gov.pl"})


class RegistryError(ValueError):
    """Base class for registry errors that are safe to show to API clients."""


class SourceNotFoundError(RegistryError):
    pass


def canonical_source_url(url: str) -> str:
    """Validate and canonicalize a whitelist URL (fragment dropped, host lowercased)."""

    try:
        return validate_url(url.strip())
    except InvalidUrlError as exc:
        raise RegistryError(f"invalid URL: {exc}") from None


def _slug(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    raw = f"{host} {parts.path}".lower()
    return _ID_CHARS.sub("-", raw).strip("-")[:60].strip("-") or "source"


def static_classification(url: str) -> tuple[str, dict[str, Any], list[str], str, str]:
    """Network-free detection: ``(adapter, params, domains, trust, path_prefix)``."""

    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path_prefix = parts.path if parts.path not in {"", "/"} else "/"
    if is_govpl_url(url):
        site_id = site_id_from_url(url)
        return (
            "govpl_search",
            {"site_id": site_id},
            ["www.gov.pl"],
            "official",
            f"/web/{site_id}" if site_id else "/",
        )
    bare = host.removeprefix("www.")
    if bare.endswith(".wikipedia.org"):
        # Encyclopaedic context, not an official statement.
        return "wikipedia", {"lang": bare.split(".", 1)[0]}, [bare], "other", "/"
    if bare in SEJM_ELI_HOSTS:
        return "sejm_eli", {}, sorted(SEJM_ELI_HOSTS), "official", "/"
    if bare in KNOWN_PUBLISHERS:
        return "fact_check_publisher", {"site": bare}, [bare], "fact_checker", "/"
    return PENDING_ADAPTER, {}, [bare], "official", path_prefix


def new_source(
    url: str,
    *,
    name: str | None = None,
    topics: Iterable[str] = (),
    description: str = "",
    trust: str | None = None,
    existing_ids: Iterable[str] = (),
) -> TrustedSource:
    canonical = canonical_source_url(url)
    adapter, params, domains, default_trust, path_prefix = static_classification(canonical)
    taken = set(existing_ids)
    base_id = _slug(canonical)
    source_id, counter = base_id, 2
    while source_id in taken:
        source_id, counter = f"{base_id}-{counter}", counter + 1
    return TrustedSource(
        id=source_id,
        url=canonical,
        name=(name or "").strip() or urlsplit(canonical).hostname or canonical,
        adapter=adapter,
        params=params,
        domains=domains,
        path_prefix=path_prefix,
        trust=trust or default_trust,  # type: ignore[arg-type]
        topics=[topic.strip() for topic in topics if topic and topic.strip()],
        description=description.strip(),
        added_at=datetime.now(UTC),
    )


class SourceRegistry:
    def __init__(self, store: SourceStore | None = None, *, refresh_seconds: float = 300.0):
        self._store = store or StaticSourceStore()
        self._refresh_seconds = refresh_seconds
        self._lock = threading.RLock()
        self._sources: dict[str, TrustedSource] = {}
        self._detected: dict[str, dict[str, Any]] = {}
        self._loaded_at: float | None = None

    def refresh(self) -> None:
        """Reload the list from the store, keeping runtime detection results."""

        sources: dict[str, TrustedSource] = {}
        seen_urls: set[str] = set()
        for entry in self._store.load():
            try:
                source = new_source(
                    entry.url,
                    name=entry.name,
                    topics=entry.topics,
                    description=entry.description,
                    existing_ids=sources,
                )
            except (RegistryError, ValidationError) as exc:
                logger.warning("skipping invalid whitelist entry: %s", type(exc).__name__)
                continue
            if source.url in seen_urls:
                continue
            seen_urls.add(source.url)
            update: dict[str, Any] = {"enabled": entry.enabled}
            if entry.adapter:
                update.update(adapter=entry.adapter, params=dict(entry.params) or source.params,
                              adapter_locked=True)
            source = source.model_copy(update=update)
            detected = self._detected.get(source.url)
            if detected:
                if source.adapter_locked:
                    detected = {"last_check": detected.get("last_check")}
                if source.description:
                    detected = {key: value for key, value in detected.items() if key != "description"}
                source = source.model_copy(update=detected)
            sources[source.id] = source
        with self._lock:
            self._sources = sources
            self._loaded_at = time.monotonic()

    def _ensure_loaded(self) -> None:
        loaded_at = self._loaded_at
        if loaded_at is None or time.monotonic() - loaded_at >= self._refresh_seconds:
            self.refresh()

    # -- queries -----------------------------------------------------------------------------

    def list(self, *, enabled_only: bool = False) -> list[TrustedSource]:
        self._ensure_loaded()
        with self._lock:
            sources = list(self._sources.values())
        return [source for source in sources if source.enabled] if enabled_only else sources

    def get(self, source_id: str) -> TrustedSource:
        self._ensure_loaded()
        with self._lock:
            try:
                return self._sources[source_id]
            except KeyError:
                raise SourceNotFoundError(f"unknown source: {source_id}") from None

    def find_by_url(self, url: str) -> TrustedSource | None:
        canonical = canonical_source_url(url)
        return next((source for source in self.list() if source.url == canonical), None)

    # -- runtime state -----------------------------------------------------------------------

    def save(self, source: TrustedSource) -> TrustedSource:
        """Remember detection results for ``source`` (in memory, not in the store)."""

        validated = TrustedSource.model_validate(source.model_dump())
        with self._lock:
            if validated.id not in self._sources:
                raise SourceNotFoundError(f"unknown source: {validated.id}")
            self._detected[validated.url] = {
                name: getattr(validated, name) for name in _DETECTED_FIELDS
            }
            self._sources[validated.id] = validated
        return validated


_default: SourceRegistry | None = None
_default_lock = threading.Lock()


def default_registry() -> SourceRegistry:
    global _default
    with _default_lock:
        if _default is None:
            from .store import default_store

            _default = SourceRegistry(store=default_store())
        return _default
