"""Silnik maskowania: zbiera trafienia wszystkich reguł, rozstrzyga nakładanie i podmienia tekst."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .rules import CONTEXT_BEFORE, RULES, UNIT_AFTER, URL, Keyword, Rule

# Ile znaków przed wartością przeszukujemy w poszukiwaniu słowa-klucza („PESEL: …”).
_KEYWORD_WINDOW = 30
_CONTEXT_WINDOW = 20


@dataclass(frozen=True)
class Entity:
    """Jedna zamaskowana wartość. ``start`` i ``end`` to pozycje w tekście wejściowym."""

    label: str
    placeholder: str
    start: int
    end: int


@dataclass(frozen=True)
class MaskingResult:
    text: str
    entities: list[Entity] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        """Liczba zamaskowanych wartości według typu (bez samych wartości – bezpieczne do logów)."""
        return dict(Counter(e.label for e in self.entities))

    @property
    def changed(self) -> bool:
        return bool(self.entities)


@dataclass(frozen=True)
class _Candidate:
    rule: Rule
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start


def _value_span(match: re.Match[str]) -> tuple[int, int]:
    return match.span("v") if "v" in match.re.groupindex else match.span()


def _accepts(rule: Rule, text: str, start: int, end: int) -> bool:
    value = text[start:end]
    keyword_found = rule.keyword is not None and bool(
        rule.keyword.search(text, max(0, start - _KEYWORD_WINDOW), start)
    )
    if rule.keyword_mode is Keyword.REQUIRED and not keyword_found:
        return False
    if rule.keyword_mode is Keyword.BYPASS and keyword_found:
        return True
    before = text[max(0, start - _CONTEXT_WINDOW) : start]
    if rule.blocked_after is not None and rule.blocked_after.search(before):
        return False
    if rule.weak:
        if UNIT_AFTER.match(text, end):
            return False
        if CONTEXT_BEFORE.search(before):
            return False
        # „500 000 000” to raczej kwota niż numer telefonu.
        if rule.label == "TELEFON" and re.search(r"[ \-]000[ \-]?000$", value):
            return False
    return rule.validate is None or rule.validate(value)


def _candidates(text: str) -> list[_Candidate]:
    urls = [m.span() for m in URL.finditer(text)]
    found: list[_Candidate] = []
    for rule in RULES:
        for match in rule.pattern.finditer(text):
            start, end = _value_span(match)
            if start == end:
                continue
            # Liczby w linkach (identyfikatory artykułów) to nie dane osobowe.
            if rule.label != "EMAIL" and any(u0 <= start and end <= u1 for u0, u1 in urls):
                continue
            if _accepts(rule, text, start, end):
                found.append(_Candidate(rule, start, end))
    return found


def _normalize(label: str, value: str) -> str:
    compact = re.sub(r"[\s\-()./]", "", value).casefold()
    if label == "TELEFON":
        compact = re.sub(r"^(?:\+|00)48", "", compact)
    elif label in {"NIP", "NR_KONTA"}:
        compact = compact.removeprefix("pl")
    return compact


def mask_personal_data(text: str) -> MaskingResult:
    """Zastępuje dane osobowe znacznikami ``[TYP_N]``; imiona i nazwiska zostają.

    Ta sama wartość w kilku miejscach dostaje ten sam numer, różne wartości tego
    samego typu – kolejne numery. Znaczniki są nieodwracalne.
    """
    if not text:
        return MaskingResult(text=text)

    # Najpierw pewniejsze reguły, przy remisie dłuższe dopasowanie.
    ordered = sorted(_candidates(text), key=lambda c: (c.rule.priority, -c.length, c.start))
    chosen: list[_Candidate] = []
    for cand in ordered:
        if all(cand.end <= c.start or cand.start >= c.end for c in chosen):
            chosen.append(cand)
    chosen.sort(key=lambda c: c.start)

    numbers: dict[tuple[str, str], int] = {}
    per_label: Counter[str] = Counter()
    entities: list[Entity] = []
    parts: list[str] = []
    cursor = 0
    for cand in chosen:
        label = cand.rule.label
        key = (label, _normalize(label, text[cand.start : cand.end]))
        if key not in numbers:
            per_label[label] += 1
            numbers[key] = per_label[label]
        placeholder = f"[{label}_{numbers[key]}]"
        entities.append(Entity(label, placeholder, cand.start, cand.end))
        parts.append(text[cursor : cand.start])
        parts.append(placeholder)
        cursor = cand.end
    parts.append(text[cursor:])
    return MaskingResult(text="".join(parts), entities=entities)
