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
  ``nieweryfikowalny`` albo brak jakichkolwiek źródeł). Gdy o ten sam temat pyta co
  najmniej ``info_gap_min_users`` różnych osób w oknie czasu, temat przechodzi w stan
  ``aktywna`` i powstaje alert. Pierwsze rozstrzygnięcie ze źródłami zamyka lukę.
* **kampania dezinformacyjna** — co najmniej ``disinfo_min_users`` różnych osób pyta w
  krótkim oknie o twierdzenie ocenione jako fałsz.
* **niebezpieczny użytkownik** — powtarzające się zapytania o terroryzm, broń, materiały
  wybuchowe itp. (``safety.classify``): alert, a przy zamiarze operacyjnym blokada czasowa.
"""

from __future__ import annotations

import contextlib
import hashlib
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from . import topics
from .runtime import MonitoringConfig, RuntimeConfigStore
from .safety import classify
from .settings import AdminSettings, user_label
from .store import AdminStore, new_id

GAP_VERDICTS = frozenset({"brak_wystarczajacych_danych", "nieweryfikowalny", "brak_danych"})
FALSE_VERDICTS = frozenset({"falsz", "falszywy", "zawiera_falsz"})
TRUE_VERDICTS = frozenset({"prawda", "prawdziwy"})

GAP_STATUSES = ("brak", "podejrzenie", "aktywna", "w_uzupelnianiu", "zamknieta", "odrzucona")
ADMIN_GAP_STATUSES = ("aktywna", "w_uzupelnianiu", "zamknieta", "odrzucona")
ALERT_STATUSES = ("otwarty", "w_analizie", "rozwiazany", "falszywy_alarm")
ALERT_TYPES = ("luka_informacyjna", "kampania_dezinformacyjna", "niebezpieczny_uzytkownik")
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
    ) -> ScreenDecision:
        """Zarejestruj zapytanie i zdecyduj, czy wolno je przetwarzać."""
        now, cfg = self.now(), self.config
        ts = iso(now)
        key = self.settings.user_key(user_id)
        safety = classify(text)
        query_id = new_id()
        flags = [f"niebezpieczne:{name}" for name in safety.categories]

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
        self.store.touch_user(key, user_label(user_id), ts, dangerous=safety.dangerous)

        blocked_until = self._blocked_until(key, ts)
        if blocked_until is None and safety.dangerous:
            blocked_until = self._watch_dangerous_user(key, now, cfg)

        decision = ScreenDecision(query_id=query_id, allowed=True, safety=safety.as_dict())
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
                status, users = self._update_gap(topic_id, now, cfg)
            else:
                if kind in ("prawda", "falsz"):
                    self._close_gap_automatically(topic_id, now)
                row = self.store.topic_row(topic_id) or {}
                status, users = row.get("gap_status", "brak"), row.get("gap_users", 0)
            disinfo = kind == "falsz" and self._watch_disinformation(topic_id, now, cfg)
            states.append(ClaimState(claim.text, topic_id, kind, status, users, disinfo))

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
            users = max(s.info_gap_users for s in active_gaps)
            message = (
                "Ten temat jest oznaczony jako luka informacyjna: nie mamy wiarygodnych źródeł, "
                f"a pytało o niego już {persons(users)}. Zgłosiliśmy go do uzupełnienia."
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
    ) -> tuple[ScreenDecision, CompletionResult | None]:
        """Zapis po fakcie (gdy potok już się wykonał): screen + complete."""
        decision = self.screen(user_id=user_id, text=text, channel=channel)
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

    def _update_gap(self, topic_id: str, now: datetime, cfg: MonitoringConfig) -> tuple[str, int]:
        topic = self.store.topic_row(topic_id) or {}
        status = topic.get("gap_status", "brak")
        since = iso(now - timedelta(hours=cfg.info_gap_window_hours))
        if status in ("zamknieta", "odrzucona") and (topic.get("gap_updated_at") or "") > since:
            since = topic["gap_updated_at"]  # po decyzji admina liczymy od nowa
        users = self.store.distinct_users(topic_id, "luka", since)
        ts = iso(now)

        if status in ("aktywna", "w_uzupelnianiu"):
            self.store.set_gap(topic_id, gap_users=users)
        elif users >= cfg.info_gap_min_users:
            status = "aktywna"
            self.store.set_gap(
                topic_id, gap_status=status, gap_since=ts, gap_users=users, gap_updated_at=ts
            )
            _log("admin_info_gap", "warning", topic_id=topic_id, users=users)
        elif status != "odrzucona":
            status = "podejrzenie"
            self.store.set_gap(topic_id, gap_status=status, gap_users=users, gap_updated_at=ts)

        if status in ("aktywna", "w_uzupelnianiu"):
            self._upsert_alert(
                "luka_informacyjna",
                topic_id,
                now,
                title=f"Luka informacyjna: {topic.get('label', '')[:120]}",
                severity="wysoka" if users >= 3 * cfg.info_gap_min_users else "srednia",
                count=self.store.claim_count(topic_id, "luka", since),
                users=users,
                details={"temat": topic.get("label"), "okno_h": cfg.info_gap_window_hours},
            )
        return status, users

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
