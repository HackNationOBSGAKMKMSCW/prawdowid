"""Raport zagrożeń z logów observability (``GET /api/admin/threats``).

Źródłem są zdarzenia z pliku logów (JSON Lines, ``LOG_FILE``), a dziennik zapytań tylko je
uzupełnia (pseudonim, kanał, treść zapytania, stan alertu):

* **prompt injection** — ``prompt_injection``: wzorce w tekście użytkownika (monitor,
  ``InputSanitizer``) i w pobranych źródłach (wstrzyknięcie pośrednie);
* **ataki manipulacyjne** — ``admin_alert`` typu ``kampania_dezinformacyjna``: wiele osób w
  krótkim czasie sprawdza tę samą fałszywą informację;
* **informacje krytyczne** — ``admin_sensitive_query`` i ``admin_query_refused``: terroryzm,
  broń, materiały wybuchowe i inne kategorie ``safety.classify``. Bez danych o osobach.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

INJECTION = "prompt_injection"
CAMPAIGN = "kampania_dezinformacyjna"
SENSITIVE = ("admin_sensitive_query", "admin_query_refused")
RECENT = 50


def _when(event: dict[str, Any]) -> datetime | None:
    raw = str(event.get("ts") or "")
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _buckets(since: datetime, now: datetime, hours: int) -> list[str]:
    """Wszystkie przedziały okresu (także puste), żeby wykres miał ciągłą oś czasu."""
    step = timedelta(hours=1) if hours <= 48 else timedelta(days=1)
    out, moment = [], since
    while moment <= now:
        label = _bucket(moment, hours)
        if not out or out[-1] != label:
            out.append(label)
        moment += step
    last = _bucket(now, hours)
    if out[-1] != last:
        out.append(last)
    return out


def _bucket(moment: datetime, hours: int) -> str:
    """Godzina dla okna do 2 dni, inaczej doba."""
    if hours <= 48:
        return _iso(moment.replace(minute=0, second=0, microsecond=0))
    return _iso(moment.replace(hour=0, minute=0, second=0, microsecond=0))


class _Lookup:
    """Uzupełnienia z dziennika zapytań; każda pozycja czytana raz."""

    def __init__(self, store: Any) -> None:
        self.store = store
        self._queries: dict[str, dict[str, Any] | None] = {}
        self._by_request: dict[str, dict[str, Any] | None] = {}
        self._alerts: dict[str, dict[str, Any] | None] = {}

    def query(self, query_id: str | None, request_id: str | None) -> dict[str, Any] | None:
        if query_id:
            if query_id not in self._queries:
                self._queries[query_id] = self._safe(self.store.get_query, query_id)
            return self._queries[query_id]
        if request_id:
            if request_id not in self._by_request:
                self._by_request[request_id] = self._safe(self.store.query_by_request, request_id)
            return self._by_request[request_id]
        return None

    def alert(self, alert_id: str | None) -> dict[str, Any] | None:
        if not alert_id:
            return None
        if alert_id not in self._alerts:
            self._alerts[alert_id] = self._safe(self.store.get_alert, alert_id)
        return self._alerts[alert_id]

    @staticmethod
    def _safe(fn: Any, *args: Any) -> Any:
        try:
            return fn(*args)
        except Exception:  # noqa: BLE001 - raport z samych logów, gdy rejestr nie odpowiada
            return None


def _who(event: dict[str, Any], query: dict[str, Any] | None) -> dict[str, Any]:
    """Kanał i zapytanie zdarzenia — bez danych o osobie (starsze logi mogą je mieć)."""
    return {
        "channel": event.get("channel") or (query or {}).get("channel"),
        "query_id": (query or {}).get("id") or event.get("query_id"),
        "text": (query or {}).get("text"),
    }


def threat_report(
    events: Iterable[dict[str, Any]],
    store: Any,
    *,
    hours: int = 24,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    since = now - timedelta(hours=hours)
    lookup = _Lookup(store)

    scanned = 0
    timeline: dict[str, Counter[str]] = {}
    injections: list[dict[str, Any]] = []
    critical: list[dict[str, Any]] = []
    campaigns: dict[str, dict[str, Any]] = {}

    for event in events:
        moment = _when(event)
        if moment is None or moment < since:
            continue
        scanned += 1
        name = event.get("event")
        kind = None
        if name == INJECTION:
            kind = "prompt_injection"
            injections.append({**event, "_at": moment})
        elif name == "admin_alert" and event.get("alert_type") == CAMPAIGN:
            kind = "manipulation"
            alert_id = str(event.get("alert_id") or "")
            entry = campaigns.setdefault(
                alert_id, {"alert_id": alert_id, "signals": 0, "first_signal": moment, "peak_users": 0}
            )
            entry["signals"] += 1
            entry["last_signal"] = moment
            entry["peak_users"] = max(entry["peak_users"], int(event.get("users") or 0))
        elif name in SENSITIVE:
            kind = "critical"
            critical.append({**event, "_at": moment})
        if kind:
            timeline.setdefault(_bucket(moment, hours), Counter())[kind] += 1

    # --- prompt injection ------------------------------------------------------------
    by_text = Counter(str(e.get("text_sha256")) for e in injections if e.get("text_sha256"))
    recent_injections = []
    for event in sorted(injections, key=lambda e: e["_at"], reverse=True):
        query = lookup.query(event.get("query_id"), event.get("request_id"))
        who = _who(event, query)
        if len(recent_injections) < RECENT:
            recent_injections.append(
                {
                    "ts": _iso(event["_at"]),
                    "request_id": event.get("request_id"),
                    "source": event.get("source"),
                    "kind": event.get("kind"),
                    "detector": event.get("detector"),
                    "pattern": event.get("pattern"),
                    "snippet": event.get("snippet"),
                    "text_sha256": event.get("text_sha256"),
                    "repeats": by_text.get(str(event.get("text_sha256")), 1),
                    **who,
                }
            )

    # --- ataki manipulacyjne (kampanie dezinformacyjne) --------------------------------
    campaign_list = []
    for entry in campaigns.values():
        alert = lookup.alert(entry["alert_id"]) or {}
        details = alert.get("details") or {}
        campaign_list.append(
            {
                "alert_id": entry["alert_id"] or None,
                "title": alert.get("title") or "Możliwy atak dezinformacyjny",
                "claim": details.get("temat") or alert.get("subject"),
                "topic_id": alert.get("subject"),
                "status": alert.get("status"),
                "severity": alert.get("severity"),
                "users": max(int(alert.get("users") or 0), entry["peak_users"]),
                "count": alert.get("count"),
                "signals": entry["signals"],
                "first_signal": _iso(entry["first_signal"]),
                "last_signal": _iso(entry["last_signal"]),
            }
        )
    campaign_list.sort(key=lambda c: c["last_signal"], reverse=True)

    # --- informacje krytyczne ---------------------------------------------------------
    categories: Counter[str] = Counter()
    severities: Counter[str] = Counter()
    recent_critical = []
    for event in sorted(critical, key=lambda e: e["_at"], reverse=True):
        names = [str(c) for c in event.get("categories") or []]
        categories.update(names)
        severities[str(event.get("severity") or "brak")] += 1
        query = lookup.query(event.get("query_id"), event.get("request_id"))
        who = _who(event, query)
        if len(recent_critical) < RECENT:
            recent_critical.append(
                {
                    "ts": _iso(event["_at"]),
                    "refused": event.get("event") == "admin_query_refused",
                    "reason": event.get("reason"),
                    "severity": event.get("severity"),
                    "categories": names,
                    "request_id": event.get("request_id"),
                    **who,
                }
            )
    return {
        "since": _iso(since),
        "until": _iso(now),
        "hours": hours,
        "events_scanned": scanned,
        "summary": {
            "prompt_injection": len(injections),
            "manipulation_campaigns": len(campaign_list),
            "critical_queries": len(critical),
            "refused": sum(1 for e in critical if e.get("event") == "admin_query_refused"),
        },
        "timeline": [
            {
                "bucket": bucket,
                "prompt_injection": counts["prompt_injection"],
                "manipulation": counts["manipulation"],
                "critical": counts["critical"],
            }
            for bucket, counts in (
                (bucket, timeline.get(bucket, Counter())) for bucket in _buckets(since, now, hours)
            )
        ],
        "prompt_injection": {
            "by_source": dict(Counter(str(e.get("source") or "?") for e in injections)),
            "by_detector": dict(Counter(str(e.get("detector") or "?") for e in injections)),
            "repeated_texts": sum(1 for n in by_text.values() if n > 1),
            "recent": recent_injections,
        },
        "manipulation": {"campaigns": campaign_list},
        "critical": {
            "by_category": dict(categories.most_common()),
            "by_severity": dict(severities),
            "recent": recent_critical,
        },
    }
