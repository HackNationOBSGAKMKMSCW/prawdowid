"""Rejestr zapytań użytkowników i reguły czujności dla panelu admina.

Przepływ dla jednego zapytania::

    decision = monitor.screen(text=..., channel="whatsapp")
    if not decision.allowed:
        return decision.message  # prośba o instrukcje przemocy (treść wysokiego ryzyka)
    ...  # textAnalysis -> apiReading -> werdykt
    result = monitor.complete(decision.query_id, claims=[...], verdict=...)
    # result.message: komunikat o luce informacyjnej do dołączenia do odpowiedzi

Bez danych o użytkownikach aplikacji: nie zapisujemy numerów telefonów, adresów IP,
pseudonimów ani końcówek identyfikatorów. Każde zapytanie jest anonimowe
(``user_key = ANONYMOUS_KEY``), więc nie ma rejestru użytkowników ani blokad, a reguły liczą
zapytania, nie osoby.

Reguły (progi w ``RuntimeConfig.monitoring``, zmieniane przez admina):

* **luka informacyjna** — twierdzenie bez rozstrzygnięcia (``brak_wystarczajacych_danych``,
  ``nieweryfikowalny`` albo brak jakichkolwiek źródeł). Gdy o ten sam temat zapytano co
  najmniej ``info_gap_min_queries`` razy w oknie ``info_gap_window_hours``, temat przechodzi
  w stan ``aktywna`` i powstaje alert. Pierwsze rozstrzygnięcie ze źródłami zamyka lukę.
* **kampania dezinformacyjna** — co najmniej ``disinfo_min_users`` zapytań w krótkim oknie
  o twierdzenie ocenione jako fałsz (nazwa pola historyczna: liczone są zapytania).
* **treści niebezpieczne** — zapytania o terroryzm, broń, materiały wybuchowe itp.
  (``safety.classify``): od ``dangerous_alert_after`` takich zapytań w oknie
  ``dangerous_window_hours`` alert zbiorczy; prośba o instrukcję lub zdobycie (wysokie
  ryzyko) jest odrzucana, gdy ``refuse_high_risk``.
* **próba prompt injection** — tekst z poleceniami dla modelu (``observability.injection``):
  flaga ``prompt_injection``, zdarzenie w logach, a od ``injection_alert_after`` prób w oknie
  ``dangerous_window_hours`` alert zbiorczy. Tekst nadal jest sprawdzany jako dane.
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
from .settings import AdminSettings
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
    "tresci_niebezpieczne",
    "prompt_injection",
    "rosyjska_dezinformacja",
    "sql_injection",
)
# Alerty-zdarzenia: każde wykrycie jest rejestrowane (licznik + lista ostatnich wystąpień).
OCCURRENCE_LIMIT = 20
SOURCES_LIMIT = 500
DISINFO_LABEL = "Zweryfikowana rosyjska dezinformacja"
INJECTION_FLAG = "prompt_injection"
TOPIC_LOOKBACK = timedelta(days=30)

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


# Jedyna wartość ``user_key`` w rejestrze: nie identyfikuje nikogo (migracja 0010 nadpisała nią
# wcześniejsze pseudonimy).
ANONYMOUS_KEY = "anonim"


def gap_measure(
    cfg: MonitoringConfig, *, users: int = 0, queries: int, reporters: int | None = None
) -> tuple[int, int]:
    """(liczba zapytań bez rozstrzygnięcia, próg). Bez danych o osobach liczymy zapytania."""
    return queries, cfg.info_gap_min_queries


def _log(event: str, level: str = "info", **fields: Any) -> None:
    with contextlib.suppress(Exception):
        from observability import log_event

        log_event(event, level=level, **fields)


def _scan_injection(text: str) -> Any:
    """Wzorce prompt injection z observability; ``None`` bez dopasowania lub modułu."""
    with contextlib.suppress(Exception):
        from observability.injection import scan

        return scan(text)
    return None


def _log_injection(text: str, match: Any, **fields: Any) -> None:
    with contextlib.suppress(Exception):
        from observability.events import log_prompt_injection

        log_prompt_injection(
            text=text,
            pattern=match.pattern,
            source="input",
            kind="input_pattern",
            snippet=match.snippet,
            detector="monitor",
            **fields,
        )


def _request_id() -> str | None:
    with contextlib.suppress(Exception):
        from observability import current_request_id

        return current_request_id()
    return None


def _same_request(occurrences: Sequence[Any], request_id: str | None) -> int | None:
    """Indeks wystąpienia z tego samego żądania (``request_id``), jeśli już jest."""
    if not request_id:
        return None
    for index, item in enumerate(occurrences):
        if isinstance(item, dict) and item.get("request_id") == request_id:
            return index
    return None


def _merge_occurrence(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Jedno wystąpienie z dwóch zgłoszeń: listy łączone, puste pola uzupełniane."""
    merged = dict(old)
    for name, value in new.items():
        if name == "ts":
            continue
        if isinstance(value, list) and isinstance(merged.get(name), list):
            merged[name] = list(dict.fromkeys([*merged[name], *value]))
        elif merged.get(name) in (None, "", []):
            merged[name] = value
    return merged


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
        return ANONYMOUS_KEY

    @property
    def config(self) -> MonitoringConfig:
        return self.runtime.load().monitoring

    def now(self) -> datetime:
        return self._clock()

    # --- przed potokiem ----------------------------------------------------------------

    def screen(
        self,
        *,
        text: str,
        channel: str = "api",
        request_id: str | None = None,
        account_id: int | None = None,
        query_id: str | None = None,
        user_id: str | None = None,
        anonymous: bool = True,
    ) -> ScreenDecision:
        """Zarejestruj zapytanie i zdecyduj, czy wolno je przetwarzać.

        Zapis jest anonimowy: ``user_id`` (np. numer telefonu, adres IP) i ``anonymous`` są
        przyjmowane tylko dla zgodności wywołań i niczego nie zapisują. Odmowa zależy wyłącznie
        od treści (prośba o instrukcje przemocy).

        ``query_id``: własny identyfikator (np. id wyniku z ``/api/check``), żeby późniejsze
        zgłoszenie błędu trafiło do tego samego wpisu; domyślnie nowy.
        """
        del user_id, anonymous  # nie zbieramy danych o użytkownikach aplikacji
        now, cfg = self.now(), self.config
        ts = iso(now)
        safety = classify(text)
        query_id = (query_id or new_id())[:32]
        flags = [f"niebezpieczne:{name}" for name in safety.categories]
        injection = _scan_injection(text)
        if injection is not None:
            flags.append(INJECTION_FLAG)
        sqli_patterns = scan_text(text)
        if sqli_patterns:
            flags.append("sql_injection")

        self.store.insert_query(
            id=query_id,
            ts=ts,
            user_key=ANONYMOUS_KEY,
            user_label=None,
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
        if sqli_patterns:
            # Ten sam tekst widzi też middleware HTTP (``request_audit``); po ``request_id``
            # oba zgłoszenia łączą się w jedno wystąpienie alertu.
            try:  # powiadomienie nigdy nie zmienia decyzji ani nie psuje zapytania
                self.register_sql_injection(
                    channel=channel,
                    source=None,
                    patterns=sqli_patterns,
                    locations=["tresc_wiadomosci"],
                    query_id=query_id,
                    request_id=request_id,
                )
            except Exception as exc:  # noqa: BLE001
                _log("admin_alert_failed", "warning", error_type=type(exc).__name__)
        if injection is not None:
            _log_injection(text, injection, query_id=query_id, channel=channel[:32])
            self._watch_injection(now, cfg)
        if safety.dangerous:
            self._watch_dangerous_content(now, cfg)

        if safety.severity == "wysoki" and cfg.refuse_high_risk:
            decision.allowed = False
            decision.reason = "niebezpieczna_tresc"
            decision.message = MESSAGE_HIGH_RISK
            flags.append(f"odrzucone:{decision.reason}")
            self.store.update_query(query_id, status="odrzucone", flags=flags, completed_at=ts)
            _log(
                "admin_query_refused",
                "warning",
                reason=decision.reason,
                query_id=query_id,
                channel=channel[:32],
                **safety.as_dict(),
            )
        elif safety.dangerous:
            _log(
                "admin_sensitive_query",
                "warning",
                query_id=query_id,
                channel=channel[:32],
                **safety.as_dict(),
            )
        return decision

    def _watch_dangerous_content(self, now: datetime, cfg: MonitoringConfig) -> None:
        """Alert zbiorczy, gdy w oknie przybywa zapytań o treści niebezpieczne."""
        since = iso(now - timedelta(hours=cfg.dangerous_window_hours))
        total = self.store.dangerous_count(since)
        if total < cfg.dangerous_alert_after:
            return
        high = self.store.dangerous_count(since, severity="wysoki")
        self._upsert_alert(
            "tresci_niebezpieczne",
            "wszystkie",
            now,
            title=f"Zapytania o treści niebezpieczne ({total})",
            severity="wysoka" if high else "srednia",
            count=total,
            users=0,
            details={
                "okno_h": cfg.dangerous_window_hours,
                "wysokie_ryzyko": high,
                "kategorie": self._recent_categories(since),
            },
        )

    def _watch_injection(self, now: datetime, cfg: MonitoringConfig) -> None:
        """Alert zbiorczy, gdy w oknie powtarzają się próby sterowania modelem."""
        since = iso(now - timedelta(hours=cfg.dangerous_window_hours))
        _, attempts = self.store.list_queries(flag=INJECTION_FLAG, since=since, limit=1)
        if attempts >= cfg.injection_alert_after:
            self._upsert_alert(
                "prompt_injection",
                "wszystkie",
                now,
                title=f"Powtarzające się próby prompt injection ({attempts})",
                severity="wysoka" if attempts >= 2 * cfg.injection_alert_after else "srednia",
                count=attempts,
                users=0,
                details={"okno_h": cfg.dangerous_window_hours},
            )

    def _recent_categories(self, since: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        queries, _ = self.store.list_queries(flag="niebezpieczne", since=since, limit=500)
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
            asked = f"pytano o niego już {times(max(s.info_gap_queries for s in active_gaps))}"
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
        text: str,
        channel: str = "api",
        claims: Sequence[ClaimInput] = (),
        verdict: str | None = None,
        sources_count: int | None = None,
        error: str | None = None,
        user_id: str | None = None,
        anonymous: bool = True,
    ) -> tuple[ScreenDecision, CompletionResult | None]:
        """Zapis po fakcie (gdy potok już się wykonał): screen + complete. Anonimowo."""
        del user_id, anonymous
        decision = self.screen(text=text, channel=channel)
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
        """Policz zapytania bez pokrycia w oknie; przy progu: luka aktywna + alert."""
        topic = self.store.topic_row(topic_id) or {}
        status = topic.get("gap_status", "brak")
        since = iso(now - timedelta(hours=cfg.info_gap_window_hours))
        if status in ("zamknieta", "odrzucona") and (topic.get("gap_updated_at") or "") > since:
            since = topic["gap_updated_at"]  # po decyzji admina liczymy od nowa
        counts = self.store.gap_counts(topic_id, "luka", since, self.anonymous_key)
        # Bez danych o osobach: liczba „osób” zawsze 0, liczą się zapytania.
        users, queries = 0, counts["queries"]
        counted, threshold = gap_measure(cfg, queries=queries, reporters=counts["reporters"])
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
                    "liczone_po": "zapytania",
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
        queries = self.store.distinct_queries(topic_id, "falsz", since)
        if queries < cfg.disinfo_min_users:  # pole historyczne: liczymy zapytania
            return False
        topic = self.store.topic_row(topic_id) or {}
        self._upsert_alert(
            "kampania_dezinformacyjna",
            topic_id,
            now,
            title=f"Możliwy atak dezinformacyjny: {topic.get('label', '')[:120]}",
            severity="wysoka" if queries >= 2 * cfg.disinfo_min_users else "srednia",
            count=queries,
            users=0,
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

    # --- zgłoszenia od użytkowników ----------------------------------------------------

    def add_report(self, query_id: str, *, reason: str, comment: str | None = None) -> bool:
        """Zgłoszenie błędu w wyniku (np. ``POST /api/check/{id}/report``).

        Wpis dostaje flagę ``zgloszenie:<powód>`` (filtr w historii weryfikacji) i treść
        zgłoszenia. ``False``, gdy zapytania nie ma w dzienniku (np. już usunięte).
        """
        query = self.store.get_query(query_id)
        if query is None:
            return False
        flags = [*(query.get("flags") or []), f"zgloszenie:{reason}"]
        report = {"reason": reason, "comment": comment or None, "ts": iso(self.now())}
        self.store.update_query(query_id, flags=flags, report=report)
        _log("admin_query_reported", reason=reason)
        return True

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
            counted = gap_measure(cfg, queries=row["queries"], reporters=row["reporters"])[0]
            bucket = per_topic.get(row["topic_id"], {})
            items.append(
                {
                    **row,
                    "users": 0,  # bez danych o osobach
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
            "count_by": "zapytania",
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
        # Bez danych o osobach: każde zapytanie liczy się osobno.
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
            same = _same_request(previous.get("wystapienia", []), entry["request_id"])
            if existing and same is not None:
                # To samo żądanie zgłoszone drugi raz (np. middleware HTTP i monitor treści):
                # jedno wystąpienie, bez zwiększania licznika.
                occurrences = list(previous.get("wystapienia", []))
                occurrences[same] = _merge_occurrence(occurrences[same], entry)
                # źródło już policzone przy pierwszym zgłoszeniu (pseudonimy kanałów się różnią)
                self.store.update_alert(
                    existing["id"],
                    details={**previous, **details, "wystapienia": occurrences},
                    updated_at=ts,
                )
                return existing["id"]
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

    def purge_expired(self) -> dict[str, int]:
        before = iso(self.now() - timedelta(days=self.config.retention_days))
        return self.store.purge(before)
