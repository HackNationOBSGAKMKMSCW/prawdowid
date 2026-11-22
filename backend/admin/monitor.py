"""Rejestr zapytań użytkowników i reguły czujności dla panelu admina.

Przepływ dla jednego zapytania::

    decision = monitor.screen(user_id=..., text=..., channel="whatsapp")
    if not decision.allowed:
        return decision.message  # zablokowany / treść wysokiego ryzyka
    ...  # textAnalysis -> apiReading -> werdykt
    result = monitor.complete(decision.query_id, claims=[...], verdict=...)
    # result.message: komunikat o luce informacyjnej do dołączenia do odpowiedzi

Reguły (progi w ``RuntimeConfig.monitoring``, zmieniane przez admina):

* **luka informacyjna** — twierdzenie bez rozstrzygnięcia (``brak_wystarczajacych_danych``,
  ``nieweryfikowalny`` albo brak jakichkolwiek źródeł). Liczenie (``info_gap_count_by``):
  ``"auto"`` (domyślnie) — rozpoznana osoba (np. WhatsApp) liczy się raz, a każde anonimowe
  zapytanie ze strony osobno, próg ``info_gap_min_users``; ``"osoby"`` — tylko różne
  pseudonimy; ``"zapytania"`` — każde zapytanie, próg ``info_gap_min_queries``. Po
  przekroczeniu progu w oknie czasu temat przechodzi w stan ``aktywna`` i powstaje alert.
  Pierwsze rozstrzygnięcie ze źródłami zamyka lukę.
* **kampania dezinformacyjna** — co najmniej ``disinfo_min_users`` różnych osób pyta w
  krótkim oknie o twierdzenie ocenione jako fałsz.
* **niebezpieczny użytkownik** — powtarzające się zapytania o terroryzm, broń, materiały
  wybuchowe itp. (``safety.classify``): alert, a przy zamiarze operacyjnym blokada czasowa.
* **rosyjska dezinformacja** — twierdzenie z zapytania jest w bazie EUvsDisinfo (MCP):
  jeden alert na przypadek z bazy, każde kolejne zapytanie zwiększa licznik.
* **SQL injection** — próba wstrzyknięcia SQL w parametrach żądania albo w treści
  (``sqli.scan_*``): jeden alert na kanał, każda próba zwiększa licznik. Nic nie jest
  blokowane (zapytania do bazy są parametryzowane); w alercie nie ma wartości pól.
"""

from __future__ import annotations

import contextlib
import hashlib
import threading
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from . import topics
from .runtime import MonitoringConfig, RuntimeConfigStore
from .safety import classify
from .settings import AdminSettings, user_label
from .sqli import scan_text
from .store import AdminStore, new_id

GAP_VERDICTS = frozenset({"brak_wystarczajacych_danych", "nieweryfikowalny", "brak_danych"})
FALSE_VERDICTS = frozenset({"falsz", "falszywy", "zawiera_falsz"})
TRUE_VERDICTS = frozenset({"prawda", "prawdziwy"})

GAP_STATUSES = ("brak", "podejrzenie", "aktywna", "w_uzupelnianiu", "zamknieta", "odrzucona")
ADMIN_GAP_STATUSES = ("aktywna", "w_uzupelnianiu", "zamknieta", "odrzucona")
ALERT_STATUSES = ("otwarty", "w_analizie", "rozwiazany", "falszywy_alarm")
ALERT_TYPES = (
    "luka_informacyjna",
    "kampania_dezinformacyjna",
    "niebezpieczny_uzytkownik",
    "rosyjska_dezinformacja",
    "sql_injection",
)
# Alerty-zdarzenia: każde wykrycie jest rejestrowane (licznik + lista ostatnich wystąpień).
OCCURRENCE_LIMIT = 20
SOURCES_LIMIT = 500
DISINFO_LABEL = "Zweryfikowana rosyjska dezinformacja"
PERMANENT = "9999-12-31T23:59:59.000Z"
TOPIC_LOOKBACK = timedelta(days=30)

MESSAGE_BLOCKED = (
    "Twoje zapytania są czasowo wstrzymane z powodu powtarzających się pytań o treści "
    "niebezpieczne. Jeśli to pomyłka, skontaktuj się z administratorem serwisu."
)
MESSAGE_HIGH_RISK = (
    "Nie mogę pomóc w tej sprawie. Serwis sprawdza prawdziwość informacji i nie udziela "
    "instrukcji dotyczących broni, materiałów wybuchowych ani przemocy."
)


def iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def persons(count: int) -> str:
    """Polska odmiana: 1 osoba, 2-4 osoby, 5-21 osób, 22-24 osoby…"""
    if count == 1:
        return "1 osoba"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} osoby"
    return f"{count} osób"


def _iso_value(value: Any) -> Any:
    """Czas z bazy: tekst ISO z SQLite albo ``datetime`` z PostgreSQL -> tekst ISO (UTC)."""
    return iso(value) if isinstance(value, datetime) else value


def _day(value: Any) -> str:
    """Dzień (UTC, ``YYYY-MM-DD``) dla czasu z bazy."""
    if isinstance(value, datetime):
        return value.astimezone(UTC).date().isoformat()
    return str(value)[:10]


def times(count: int) -> str:
    """1 raz, 2 razy, 5 razy."""
    return "1 raz" if count == 1 else f"{count} razy"


ANONYMOUS_USER = "web"  # wspólny pseudonim zapisów anonimowych (strona bez logowania)


def gap_measure(
    cfg: MonitoringConfig, *, users: int, queries: int, reporters: int | None = None
) -> tuple[int, int]:
    """(wartość liczona, próg) według ``info_gap_count_by``.

    ``reporters`` (tryb ``auto``): rozpoznane osoby raz + każde anonimowe zapytanie osobno.
    """
    if cfg.info_gap_count_by == "osoby":
        return users, cfg.info_gap_min_users
    if cfg.info_gap_count_by == "zapytania":
        return queries, cfg.info_gap_min_queries
    return (users if reporters is None else reporters), cfg.info_gap_min_users


def _log(event: str, level: str = "info", **fields: Any) -> None:
    with contextlib.suppress(Exception):
        from observability import log_event

        log_event(event, level=level, **fields)


def _request_id() -> str | None:
    with contextlib.suppress(Exception):
        from observability import current_request_id

        return current_request_id()
    return None


def claim_kind(verdict: str | None, sources_count: int | None) -> str:
    if verdict in FALSE_VERDICTS:
        return "falsz"
    if verdict in TRUE_VERDICTS:
        return "prawda"
    if verdict in GAP_VERDICTS or (verdict is None and sources_count == 0):
        return "luka"
    return "inne"


@dataclass(frozen=True)
class ClaimInput:
    text: str
    verdict: str | None = None
    sources_count: int | None = None


@dataclass
class ScreenDecision:
    query_id: str
    allowed: bool
    reason: str | None = None
    message: str | None = None
    safety: dict[str, Any] = field(default_factory=dict)
    blocked_until: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimState:
    text: str
    topic_id: str
    kind: str
    info_gap_status: str
    info_gap_users: int
    disinformation_alert: bool = False
    info_gap_queries: int = 0
    info_gap_count: int = 0  # wartość porównywana z progiem w bieżącym trybie


@dataclass
class CompletionResult:
    query_id: str
    claims: list[ClaimState]
    flags: list[str]
    info_gap: bool
    message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class Monitor:
    def __init__(
        self,
        store: AdminStore,
        settings: AdminSettings | None = None,
        runtime: RuntimeConfigStore | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or AdminSettings()
        self.runtime = runtime or RuntimeConfigStore()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._events_lock = threading.Lock()  # alerty-zdarzenia: odczyt + zapis bez wyścigu

    @property
    def anonymous_key(self) -> str:
        return self.settings.user_key(ANONYMOUS_USER)

    @property
    def config(self) -> MonitoringConfig:
        return self.runtime.load().monitoring

    def now(self) -> datetime:
        return self._clock()

    # --- przed potokiem ----------------------------------------------------------------

    def screen(
        self,
        *,
        user_id: str,
        text: str,
        channel: str = "api",
        request_id: str | None = None,
        account_id: int | None = None,
        anonymous: bool = False,
    ) -> ScreenDecision:
        """Zarejestruj zapytanie i zdecyduj, czy wolno je przetwarzać.

        ``anonymous=True`` (np. strona bez logowania): wszyscy dzielą jeden pseudonim kanału,
        więc nie ma rejestru użytkownika, blokad ani odmowy; flagi bezpieczeństwa zostają
        tylko informacyjne. Zapytanie liczy się do luk informacyjnych jak każde inne.
        """
        now, cfg = self.now(), self.config
        ts = iso(now)
        key = self.anonymous_key if anonymous else self.settings.user_key(user_id)
        safety = classify(text)
        query_id = new_id()
        flags = [f"niebezpieczne:{name}" for name in safety.categories]
        sqli_patterns = scan_text(text)
        if sqli_patterns:
            flags.append("sql_injection")

        self.store.insert_query(
            id=query_id,
            ts=ts,
            user_key=key,
            user_label=user_label(user_id),
            channel=channel[:32],
            text=text[: self.settings.max_text_length],
            text_sha=hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16],
            status="w_toku",
            flags=flags,
            safety=safety.as_dict(),
            request_id=request_id or _request_id(),
            account_id=account_id,
        )
        decision = ScreenDecision(query_id=query_id, allowed=True, safety=safety.as_dict())
        if sqli_patterns and not anonymous:  # strona: zgłasza to już middleware żądań
            try:  # powiadomienie nigdy nie zmienia decyzji ani nie psuje zapytania
                self.register_sql_injection(
                    channel=channel,
                    source=key,
                    source_label=user_label(user_id),
                    patterns=sqli_patterns,
                    locations=["tresc_wiadomosci"],
                    query_id=query_id,
                )
            except Exception as exc:  # noqa: BLE001
                _log("admin_alert_failed", "warning", error_type=type(exc).__name__)
        if anonymous:
            if safety.dangerous:
                _log("admin_sensitive_query", "warning", user_key=key, **safety.as_dict())
            return decision
        self.store.touch_user(key, user_label(user_id), ts, dangerous=safety.dangerous)

        blocked_until = self._blocked_until(key, ts)
        if blocked_until is None and safety.dangerous:
            blocked_until = self._watch_dangerous_user(key, now, cfg)

        if blocked_until is not None:
            decision.allowed = False
            decision.reason = "uzytkownik_zablokowany"
            decision.message = MESSAGE_BLOCKED
            decision.blocked_until = blocked_until
        elif safety.severity == "wysoki" and cfg.refuse_high_risk:
            decision.allowed = False
            decision.reason = "niebezpieczna_tresc"
            decision.message = MESSAGE_HIGH_RISK

        if not decision.allowed:
            flags.append(f"odrzucone:{decision.reason}")
            self.store.update_query(query_id, status="odrzucone", flags=flags, completed_at=ts)
            _log("admin_query_refused", "warning", reason=decision.reason, user_key=key)
        elif safety.dangerous:
            _log("admin_sensitive_query", "warning", user_key=key, **safety.as_dict())
        return decision

    def _blocked_until(self, user_key: str, ts: str) -> str | None:
        user = self.store.get_user(user_key)
        until = user and user.get("blocked_until")
        return until if until and until > ts else None

    def _watch_dangerous_user(
        self, user_key: str, now: datetime, cfg: MonitoringConfig
    ) -> str | None:
        """Alert przy powtarzających się zapytaniach; blokada przy zamiarze operacyjnym."""
        since = iso(now - timedelta(hours=cfg.dangerous_window_hours))
        total = self.store.dangerous_count(user_key, since)
        high = self.store.dangerous_count(user_key, since, severity="wysoki")
        blocked_until = None
        if cfg.auto_block and high >= cfg.dangerous_block_after:
            blocked_until = iso(now + timedelta(hours=cfg.dangerous_block_hours))
            self.store.set_block(
                user_key,
                blocked_until,
                f"automatycznie: {high} zapytań wysokiego ryzyka w ciągu "
                f"{cfg.dangerous_window_hours} h",
            )
            _log("admin_user_blocked", "warning", user_key=user_key, until=blocked_until)
        if total >= cfg.dangerous_alert_after or blocked_until:
            categories = self._recent_categories(user_key, since)
            self._upsert_alert(
                "niebezpieczny_uzytkownik",
                user_key,
                now,
                title=f"Powtarzające się zapytania o treści niebezpieczne ({total})",
                severity="wysoka" if high else "srednia",
                count=total,
                users=1,
                details={
                    "okno_h": cfg.dangerous_window_hours,
                    "wysokie_ryzyko": high,
                    "kategorie": categories,
                    "zablokowany_do": blocked_until,
                },
            )
        return blocked_until

    def _recent_categories(self, user_key: str, since: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        queries, _ = self.store.list_queries(user_key=user_key, since=since, limit=200)
        for query in queries:
            for name in (query.get("safety") or {}).get("categories", []):
                counts[name] = counts.get(name, 0) + 1
        return counts

    # --- po potoku ---------------------------------------------------------------------

    def complete(
        self,
        query_id: str,
        *,
        claims: Sequence[ClaimInput] = (),
        verdict: str | None = None,
        sources_count: int | None = None,
        error: str | None = None,
    ) -> CompletionResult:
        """Zapisz wynik weryfikacji i uruchom reguły luki informacyjnej i dezinformacji."""
        query = self.store.get_query(query_id)
        if query is None:
            raise KeyError(query_id)
        now, cfg = self.now(), self.config
        ts = iso(now)
        flags = list(query.get("flags") or [])

        if not claims and error is None and (verdict is not None or sources_count == 0):
            claims = [ClaimInput(query["text"] or "", verdict, sources_count)]

        states: list[ClaimState] = []
        for claim in claims:
            if not claim.text.strip():
                continue
            kind = claim_kind(claim.verdict, claim.sources_count)
            topic_id = self._topic_for(claim.text, ts, now)
            self.store.insert_claim(
                query_id=query_id,
                ts=ts,
                user_key=query["user_key"],
                topic_id=topic_id,
                text=claim.text[:1000],
                verdict=claim.verdict,
                kind=kind,
                sources_count=claim.sources_count,
            )
            if kind == "luka":
                status, users, queries, counted = self._update_gap(topic_id, now, cfg)
            else:
                if kind in ("prawda", "falsz"):
                    self._close_gap_automatically(topic_id, now)
                row = self.store.topic_row(topic_id) or {}
                status = row.get("gap_status", "brak")
                users, queries = row.get("gap_users", 0), row.get("gap_queries", 0)
                counted = gap_measure(cfg, users=users, queries=queries)[0]
            disinfo = kind == "falsz" and self._watch_disinformation(topic_id, now, cfg)
            states.append(
                ClaimState(claim.text, topic_id, kind, status, users, disinfo, queries, counted)
            )

        active_gaps = [s for s in states if s.info_gap_status in ("aktywna", "w_uzupelnianiu")]
        if any(s.kind == "luka" for s in states):
            flags.append("brak_danych")
        if active_gaps:
            flags.append("luka_informacyjna")
        if any(s.kind == "falsz" for s in states):
            flags.append("falsz")
        if any(s.disinformation_alert for s in states):
            flags.append("kampania_dezinformacyjna")
        if error:
            flags.append("blad")

        self.store.update_query(
            query_id,
            status="blad" if error else "zakonczone",
            verdict=verdict,
            flags=flags,
            sources_count=sources_count,
            completed_at=ts,
            error=(error or None) and error[:500],
        )
        message = None
        if active_gaps:
            if cfg.info_gap_count_by == "zapytania":
                asked = f"pytano o niego już {times(max(s.info_gap_queries for s in active_gaps))}"
            else:
                asked = f"pytało o niego już {persons(max(s.info_gap_count for s in active_gaps))}"
            message = (
                "Ten temat jest oznaczony jako luka informacyjna: nie mamy wiarygodnych źródeł, "
                f"a {asked}. Zgłosiliśmy go do uzupełnienia."
            )
        return CompletionResult(
            query_id, states, sorted(set(flags)), bool(active_gaps), message=message
        )

    def record(
        self,
        *,
        user_id: str,
        text: str,
        channel: str = "api",
        claims: Sequence[ClaimInput] = (),
        verdict: str | None = None,
        sources_count: int | None = None,
        error: str | None = None,
        anonymous: bool = False,
    ) -> tuple[ScreenDecision, CompletionResult | None]:
        """Zapis po fakcie (gdy potok już się wykonał): screen + complete."""
        decision = self.screen(user_id=user_id, text=text, channel=channel, anonymous=anonymous)
        if not decision.allowed:
            return decision, None
        result = self.complete(
            decision.query_id,
            claims=claims,
            verdict=verdict,
            sources_count=sources_count,
            error=error,
        )
        return decision, result

    # --- tematy, luki, dezinformacja ---------------------------------------------------

    def _topic_for(self, text: str, ts: str, now: datetime) -> str:
        claim_tokens = topics.tokens(text)
        best_id, best_score = None, 0.0
        for topic_id, topic_tokens in self.store.recent_topics(iso(now - TOPIC_LOOKBACK)):
            score = topics.similarity(claim_tokens, topic_tokens)
            if score > best_score:
                best_id, best_score = topic_id, score
        if best_id is not None and best_score >= topics.SIMILARITY_THRESHOLD:
            self.store.touch_topic(best_id, ts)
            return best_id
        return self.store.create_topic(label=text.strip(), tokens=claim_tokens, ts=ts)

    def _update_gap(
        self, topic_id: str, now: datetime, cfg: MonitoringConfig
    ) -> tuple[str, int, int, int]:
        """Policz zapytania i osoby bez pokrycia w oknie; przy progu: luka aktywna + alert."""
        topic = self.store.topic_row(topic_id) or {}
        status = topic.get("gap_status", "brak")
        since = iso(now - timedelta(hours=cfg.info_gap_window_hours))
        if status in ("zamknieta", "odrzucona") and (topic.get("gap_updated_at") or "") > since:
            since = topic["gap_updated_at"]  # po decyzji admina liczymy od nowa
        counts = self.store.gap_counts(topic_id, "luka", since, self.anonymous_key)
        users, queries = counts["users"], counts["queries"]
        counted, threshold = gap_measure(
            cfg, users=users, queries=queries, reporters=counts["reporters"]
        )
        ts = iso(now)
        counters = {"gap_users": users, "gap_queries": queries}

        if status in ("aktywna", "w_uzupelnianiu"):
            self.store.set_gap(topic_id, **counters)
        elif counted >= threshold:
            status = "aktywna"
            self.store.set_gap(
                topic_id, gap_status=status, gap_since=ts, gap_updated_at=ts, **counters
            )
            _log("admin_info_gap", "warning", topic_id=topic_id, users=users, queries=queries)
        elif status != "odrzucona":
            status = "podejrzenie"
            self.store.set_gap(topic_id, gap_status=status, gap_updated_at=ts, **counters)
        else:
            self.store.set_gap(topic_id, **counters)

        if status in ("aktywna", "w_uzupelnianiu"):
            self._upsert_alert(
                "luka_informacyjna",
                topic_id,
                now,
                title=f"Luka informacyjna: {topic.get('label', '')[:120]}",
                severity="wysoka" if counted >= 3 * threshold else "srednia",
                count=queries,
                users=users,
                details={
                    "temat": topic.get("label"),
                    "okno_h": cfg.info_gap_window_hours,
                    "liczone_po": cfg.info_gap_count_by,
                    "prog": threshold,
                    "wartosc": counted,
                },
            )
        return status, users, queries, counted

    def _close_gap_automatically(self, topic_id: str, now: datetime) -> None:
        topic = self.store.topic_row(topic_id) or {}
        if topic.get("gap_status") not in ("podejrzenie", "aktywna", "w_uzupelnianiu"):
            return
        ts = iso(now)
        self.store.set_gap(
            topic_id,
            gap_status="zamknieta",
            gap_note="zamknięta automatycznie: pojawiło się rozstrzygnięcie oparte na źródłach",
            gap_updated_at=ts,
        )
        alert = self.store.open_alert("luka_informacyjna", topic_id)
        if alert:
            self.store.update_alert(
                alert["id"], status="rozwiazany", note="rozstrzygnięcie ze źródłami", updated_at=ts
            )

    def _watch_disinformation(self, topic_id: str, now: datetime, cfg: MonitoringConfig) -> bool:
        since = iso(now - timedelta(hours=cfg.disinfo_window_hours))
        users = self.store.distinct_users(topic_id, "falsz", since)
        if users < cfg.disinfo_min_users:
            return False
        topic = self.store.topic_row(topic_id) or {}
        self._upsert_alert(
            "kampania_dezinformacyjna",
            topic_id,
            now,
            title=f"Możliwy atak dezinformacyjny: {topic.get('label', '')[:120]}",
            severity="wysoka" if users >= 2 * cfg.disinfo_min_users else "srednia",
            count=self.store.claim_count(topic_id, "falsz", since),
            users=users,
            details={"temat": topic.get("label"), "okno_h": cfg.disinfo_window_hours},
        )
        return True

    def _upsert_alert(
        self,
        alert_type: str,
        subject: str,
        now: datetime,
        *,
        title: str,
        severity: str,
        count: int,
        users: int,
        details: dict[str, Any],
    ) -> str:
        ts = iso(now)
        existing = self.store.open_alert(alert_type, subject)
        if existing:
            self.store.update_alert(
                existing["id"],
                severity=severity,
                count=count,
                users=users,
                last_seen=ts,
                details={**existing.get("details", {}), **details},
                updated_at=ts,
            )
            return existing["id"]
        alert_id = self.store.create_alert(
            type=alert_type,
            subject=subject,
            severity=severity,
            status="otwarty",
            title=title,
            count=count,
            users=users,
            first_seen=ts,
            last_seen=ts,
            details=details,
            updated_at=ts,
        )
        _log("admin_alert", "warning", alert_type=alert_type, alert_id=alert_id, users=users)
        return alert_id

    # --- zapytania bez pokrycia w danych: widoki panelu ---------------------------------

    def uncovered_ranking(
        self, hours: int, *, min_queries: int = 1, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        """Tematy, o które najczęściej pytano bez pokrycia w danych, z trendem dziennym."""
        now, cfg = self.now(), self.config
        start = now - timedelta(hours=hours)
        since = iso(start)
        rows, total = self.store.uncovered_ranking(
            since,
            min_queries=min_queries,
            limit=limit,
            offset=offset,
            anonymous_key=self.anonymous_key,
        )
        days = [
            (start + timedelta(days=offset_days)).date().isoformat()
            for offset_days in range((now.date() - start.date()).days + 1)
        ]
        per_topic: dict[str, dict[str, int]] = {}
        for topic_id, ts in self.store.uncovered_timestamps([r["topic_id"] for r in rows], since):
            day = _day(ts)
            bucket = per_topic.setdefault(topic_id, {})
            bucket[day] = bucket.get(day, 0) + 1
        threshold = gap_measure(cfg, users=0, queries=0)[1]
        items = []
        for row in rows:
            counted = gap_measure(
                cfg, users=row["users"], queries=row["queries"], reporters=row["reporters"]
            )[0]
            bucket = per_topic.get(row["topic_id"], {})
            items.append(
                {
                    **row,
                    "last_seen": _iso_value(row["last_seen"]),
                    "gap_since": _iso_value(row.get("gap_since")),
                    "count": counted,
                    "over_threshold": counted >= threshold,
                    "trend": [{"date": day, "queries": bucket.get(day, 0)} for day in days],
                }
            )
        return {
            "generated_at": iso(now),
            "window_hours": hours,
            "count_by": cfg.info_gap_count_by,
            "threshold": threshold,
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }

    def uncovered_summary(self, hours: int, *, top: int = 5) -> dict[str, Any]:
        """Kafelki panelu: ile zapytań bez pokrycia, ile tematów w każdym stanie, top N."""
        since = iso(self.now() - timedelta(hours=hours))
        totals = self.store.uncovered_totals(since)
        ranking = self.uncovered_ranking(hours, limit=top)
        counts = self.store.gap_status_counts()
        share = (
            round(totals["uncovered_queries"] / totals["total_queries"], 4)
            if totals["total_queries"]
            else 0.0
        )
        return {
            "generated_at": ranking["generated_at"],
            "window_hours": hours,
            "count_by": ranking["count_by"],
            "threshold": ranking["threshold"],
            "window_threshold_hours": self.config.info_gap_window_hours,
            **totals,
            "uncovered_share": share,
            "uncovered_topics": ranking["total"],
            "by_status": {status: counts.get(status, 0) for status in GAP_STATUSES[1:]},
            "top": ranking["items"],
        }

    # --- zdarzenia bezpieczeństwa i dezinformacji (powiadomienia admina) ----------------

    def register_known_disinformation(
        self,
        query_id: str | None,
        matches: Sequence[dict[str, Any]],
        *,
        channel: str = "api",
        request_id: str | None = None,
    ) -> list[str]:
        """Twierdzenia znalezione w bazie EUvsDisinfo: alert ``rosyjska_dezinformacja``.

        ``matches`` to ``claims_verdict.data.known_disinfo.matches`` z ``verification``
        (pola ``statement``, ``case_id``, ``title``, ``url``, ``reason``). Zwraca id alertów.
        """
        alert_ids = []
        query = self.store.get_query(query_id) if query_id else None
        user_key = (query or {}).get("user_key")
        # Rozpoznana osoba liczy się raz; anonimowe zapytanie (strona) — każde osobno.
        if user_key and user_key != self.anonymous_key:
            reporter = user_key
        else:
            reporter = f"zapytanie:{query_id}" if query_id else None
        for match in matches:
            url = str(match.get("url") or match.get("case_id") or "").strip()
            if not url:
                continue
            title = str(match.get("title") or url)
            statement = str(match.get("statement") or "")[:500]
            alert_ids.append(
                self._record_occurrence(
                    "rosyjska_dezinformacja",
                    hashlib.sha256(url.encode("utf-8")).hexdigest()[:16],
                    title=f"{DISINFO_LABEL}: {title[:150]}",
                    severity="wysoka",
                    details={
                        "zrodlo": str(match.get("source") or "EUvsDisinfo"),
                        "przypadek": {"tytul": title, "url": url},
                        "opis": (
                            "Użytkownik zapytał o twierdzenie, które baza EUvsDisinfo "
                            "dokumentuje jako prokremlowską dezinformację."
                        ),
                    },
                    occurrence={
                        "query_id": query_id,
                        "kanal": channel,
                        "twierdzenie": statement,
                        "uzasadnienie": str(match.get("reason") or "")[:300],
                    },
                    source=reporter,
                    request_id=request_id,
                )
            )
        if alert_ids and query is not None:
            flags = [*(query.get("flags") or []), "rosyjska_dezinformacja"]
            self.store.update_query(query_id, flags=flags)
        return alert_ids

    def register_sql_injection(
        self,
        *,
        channel: str,
        source: str | None,
        patterns: Sequence[str],
        locations: Sequence[str],
        source_label: str | None = None,
        method: str | None = None,
        path: str | None = None,
        query_id: str | None = None,
        request_id: str | None = None,
    ) -> str:
        """Próba SQL injection: alert ``sql_injection`` (jeden na kanał, licznik prób).

        Zapisywane są nazwy wzorców i pól, metoda i ścieżka — bez wartości pól.
        """
        return self._record_occurrence(
            "sql_injection",
            f"kanal:{channel}"[:64],
            title=f"Próby SQL injection ({channel})",
            severity="wysoka",
            details={
                "kanal": channel,
                "opis": (
                    "Wykryto składnię SQL injection w danych wejściowych. Żądanie nie zostało "
                    "zablokowane (zapytania do bazy są parametryzowane), ale warto sprawdzić źródło."
                ),
            },
            occurrence={
                "wzorce": list(patterns),
                "pola": list(locations)[:20],
                "metoda": method,
                "sciezka": (path or "")[:200] or None,
                "zrodlo": source_label,
                "query_id": query_id,
            },
            source=source,
            request_id=request_id,
        )

    def _record_occurrence(
        self,
        alert_type: str,
        subject: str,
        *,
        title: str,
        severity: str,
        details: dict[str, Any],
        occurrence: dict[str, Any],
        source: str | None,
        request_id: str | None = None,
    ) -> str:
        """Otwarty alert danego typu i tematu: licznik +1, ostatnie wystąpienia w ``details``.

        Odczyt i zapis są pod blokadą (w procesie), a licznik rośnie w SQL (``count + 1``).
        """
        with self._events_lock:
            now = self.now()
            ts = iso(now)
            entry = {"ts": ts, "request_id": request_id or _request_id(), **occurrence}
            existing = self.store.open_alert(alert_type, subject)
            previous = (existing or {}).get("details") or {}
            occurrences = [entry, *previous.get("wystapienia", [])][:OCCURRENCE_LIMIT]
            sources = {*previous.get("zrodla", []), *([source] if source else [])}
            merged = {
                **previous,
                **details,
                "wystapienia": occurrences,
                "zrodla": sorted(sources)[:SOURCES_LIMIT],
            }
            if existing:
                users = max(int(existing.get("users") or 0), len(sources))
                if source and source not in previous.get("zrodla", []) and len(sources) > SOURCES_LIMIT:
                    users += 1
                self.store.increment_alert(
                    existing["id"],
                    users=users,
                    severity=severity,
                    last_seen=ts,
                    details=merged,
                    updated_at=ts,
                )
                alert_id = existing["id"]
            else:
                alert_id = self.store.create_alert(
                    type=alert_type,
                    subject=subject,
                    severity=severity,
                    status="otwarty",
                    title=title[:300],
                    count=1,
                    users=len(sources),
                    first_seen=ts,
                    last_seen=ts,
                    details=merged,
                    updated_at=ts,
                )
        _log("admin_alert", "warning", alert_type=alert_type, alert_id=alert_id)
        return alert_id

    # --- działania admina --------------------------------------------------------------

    def set_alert_status(self, alert_id: str, status: str, note: str | None = None) -> dict:
        if status not in ALERT_STATUSES:
            raise ValueError(f"status alertu: {', '.join(ALERT_STATUSES)}")
        if self.store.get_alert(alert_id) is None:
            raise KeyError(alert_id)
        self.store.update_alert(alert_id, status=status, note=note, updated_at=iso(self.now()))
        return self.store.get_alert(alert_id)

    def set_gap_status(self, topic_id: str, status: str, note: str | None = None) -> dict:
        if status not in ADMIN_GAP_STATUSES:
            raise ValueError(f"status luki: {', '.join(ADMIN_GAP_STATUSES)}")
        topic = self.store.topic_row(topic_id)
        if topic is None:
            raise KeyError(topic_id)
        ts = iso(self.now())
        fields: dict[str, Any] = {"gap_status": status, "gap_note": note, "gap_updated_at": ts}
        if status == "aktywna" and not topic.get("gap_since"):
            fields["gap_since"] = ts
        self.store.set_gap(topic_id, **fields)
        alert = self.store.open_alert("luka_informacyjna", topic_id)
        if alert and status in ("zamknieta", "odrzucona"):
            self.store.update_alert(
                alert["id"],
                status="rozwiazany" if status == "zamknieta" else "falszywy_alarm",
                note=note,
                updated_at=ts,
            )
        return self.store.get_topic(topic_id)

    def block_user(self, user_key: str, hours: int | None, reason: str | None) -> dict:
        if self.store.get_user(user_key) is None:
            raise KeyError(user_key)
        until = PERMANENT if hours is None else iso(self.now() + timedelta(hours=hours))
        self.store.set_block(user_key, until, reason or "decyzja administratora")
        return self.store.get_user(user_key)

    def unblock_user(self, user_key: str) -> dict:
        if self.store.get_user(user_key) is None:
            raise KeyError(user_key)
        self.store.set_block(user_key, None, None)
        return self.store.get_user(user_key)

    def purge_expired(self) -> dict[str, int]:
        before = iso(self.now() - timedelta(days=self.config.retention_days))
        return self.store.purge(before)
