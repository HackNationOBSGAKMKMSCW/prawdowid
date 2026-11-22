"""Render the website's result (``api_models.CheckResponse``) as WhatsApp messages.

Same verdicts, labels, explanations and sources as the website's result screen
(``frontend/src/content/verdicts.ts``), only in chat form.
"""

from collections.abc import Sequence
from typing import Any

from .cloud_api import MAX_HEADER_CHARS, MAX_INTERACTIVE_BODY_CHARS
from .formatting import VerdictCard, _clip, _safe_url
from .pipeline import VerifiedReport

MAX_SOURCES_PER_CLAIM = 3
MAX_MANIPULATION_FRAGMENTS = 3
MAX_DATE_ISSUES = 3
MAX_EXPLANATION_CHARS = 700

# Labels as on the website (frontend/src/content/verdicts.ts).
VERDICT_LABELS = {
    "confirmed": "Potwierdzone",
    "false": "Fałszywe",
    "misleading": "Wprowadzające w błąd",
    "insufficient": "Brak wystarczających dowodów",
    "unverifiable": "Nie podlega weryfikacji",
}
VERDICT_ICONS = {
    "confirmed": "✅",
    "false": "❌",
    "misleading": "⚠️",
    "insufficient": "❔",
    "unverifiable": "💬",
}
MIXED_HEADER = "Różne oceny twierdzeń"
NO_CLAIMS_TEXT = (
    "*Nie znalazłem w tej wiadomości twierdzeń do sprawdzenia*\n"
    "_Opinie, życzenia i bardzo ogólne pytania trudno zweryfikować. "
    "Spróbuj napisać konkretne zdanie, np. kto, co, kiedy i gdzie._"
)
MANIPULATION_TITLES = {
    "EMOTIONAL_LANGUAGE": "gra na emocjach",
    "FEAR_APPEAL": "straszenie",
    "CONSPIRACY_FRAMING": "sugerowanie spisku",
    "FALSE_URGENCY": "sztuczny pośpiech",
    "LACK_OF_SOURCE": "brak źródła",
    "EXAGGERATION": "przesada",
    "CHERRY_PICKING": "wybiórcze fakty",
}
CAVEAT = (
    "_Ocenę przygotował automat na podstawie znalezionych źródeł. "
    "Zanim coś udostępnisz, otwórz źródła i przeczytaj uzasadnienie._"
)


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _claims(report: VerifiedReport) -> list[Any]:
    return list(_get(report.response, "claims") or [])


def _sources(claim: Any) -> list[Any]:
    return list(_get(claim, "sources") or [])


def overall(claims: Sequence[Any]) -> str | None:
    """One verdict shared by every claim, ``"mixed"`` when they differ, None without claims."""
    verdicts = {_get(claim, "verdict") for claim in claims}
    if not verdicts:
        return None
    return verdicts.pop() if len(verdicts) == 1 else "mixed"


def _header(verdict: str | None) -> str:
    return VERDICT_LABELS.get(verdict or "", MIXED_HEADER)


def _sources_word(count: int) -> str:
    if count == 1:
        return "źródło"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "źródła"
    return "źródeł"


def _source_count(claims: Sequence[Any]) -> int:
    return len({(_get(s, "url"), _get(s, "publisher")) for c in claims for s in _sources(c)})


def verified_card(report: VerifiedReport) -> VerdictCard | None:
    """Headline verdict with the claim's first linked source, or None without a link."""
    claims = _claims(report)
    verdict = overall(claims)
    if verdict is None:
        return None
    # The claim that decides the headline first: the worst one for mixed results.
    order = ["false", "misleading", "confirmed", "insufficient", "unverifiable"]
    ranked = sorted(
        claims,
        key=lambda c: order.index(_get(c, "verdict")) if _get(c, "verdict") in order else 99,
    )
    for claim in ranked:
        linked = [s for s in _sources(claim) if _safe_url(_get(s, "url"))]
        if not linked:
            continue
        source = linked[0]
        meta = " · ".join(
            part for part in (_clip(_get(source, "publisher"), 60), _get(source, "year")) if part
        )
        label = VERDICT_LABELS.get(_get(claim, "verdict"), "")
        body = (
            f"_„{_clip(_get(claim, 'text'), 300)}”_\n\n"
            f"*{label}* — {_clip(_get(claim, 'explanation'), 300)}"
        )
        if meta:
            body += f"\n\nŹródło: {meta}"
        count = _source_count(claims)
        footer = f"SprawdzTo · {count} {_sources_word(count)}"
        if report.demo:
            footer += " · dane demo"
        return VerdictCard(
            header=_header(verdict)[:MAX_HEADER_CHARS],
            body=body[:MAX_INTERACTIVE_BODY_CHARS],
            footer=footer,
            url=_get(source, "url"),
        )
    return None


def _claim_section(index: int, claim: Any) -> str:
    verdict = _get(claim, "verdict")
    lines = [
        f"*{index}.* _„{_clip(_get(claim, 'text'), 240)}”_",
        f"{VERDICT_ICONS.get(verdict, '•')} *{VERDICT_LABELS.get(verdict, verdict)}*",
    ]
    explanation = _clip(_get(claim, "explanation"), MAX_EXPLANATION_CHARS)
    if explanation:
        lines.append(explanation)
    sources = _sources(claim)[:MAX_SOURCES_PER_CLAIM]
    if sources:
        lines.append("Źródła:")
        for source in sources:
            meta = " · ".join(
                part
                for part in (_clip(_get(source, "publisher"), 80), _get(source, "year"))
                if part
            )
            url = _safe_url(_get(source, "url"))
            lines.append(f"• {meta}" + (f"\n{url}" if url else ""))
    return "\n".join(lines)


def _manipulation_section(analysis: Any) -> str | None:
    manipulation = _get(analysis, "manipulation")
    if not manipulation or not _get(manipulation, "manipulation_detected"):
        return None
    lines = [
        "*Uwaga na sposób przekazu*",
        f"_Wskaźnik manipulacji: {int(_get(manipulation, 'score') or 0)}/100._",
    ]
    for fragment in list(_get(manipulation, "fragments") or [])[:MAX_MANIPULATION_FRAGMENTS]:
        title = MANIPULATION_TITLES.get(_get(fragment, "category"), "może wpływać na Ciebie")
        quote = _clip(_get(fragment, "quote"), 120)
        explanation = _clip(_get(fragment, "explanation"), 200)
        line = f"• „{quote}” — {title}"
        if explanation:
            line += f": {explanation}"
        lines.append(line)
    return "\n".join(lines)


def _dates_section(analysis: Any) -> str | None:
    dates = _get(analysis, "dates")
    if not dates or _get(dates, "dates_consistent", True):
        return None
    issues = [
        _clip(_get(issue, "description"), 200)
        for issue in list(_get(dates, "issues") or [])
        if _get(issue, "description")
    ][:MAX_DATE_ISSUES]
    lines = ["*Daty się nie zgadzają*"]
    lines.extend(f"• {issue}" for issue in issues)
    if not issues:
        lines.append("_Daty w wiadomości nie pasują do dat w źródłach._")
    return "\n".join(lines)


def format_verified(report: VerifiedReport, *, headline: bool = True) -> str:
    """Full reply: verdict per claim with explanation and sources, then the input analysis.

    With ``headline=False`` the overall verdict is left out because a card shows it.
    """
    claims = _claims(report)
    sections: list[str] = []
    if not claims:
        sections.append(NO_CLAIMS_TEXT)
    else:
        if headline:
            verdict = overall(claims)
            icon = VERDICT_ICONS.get(verdict or "", "")
            sections.append(
                f"*Wynik sprawdzenia*\n{icon} *{_header(verdict)}*".replace("\n ", "\n")
            )
        else:
            sections.append("*Szczegóły sprawdzenia*")
        sections.extend(_claim_section(index, claim) for index, claim in enumerate(claims, 1))

    analysis = _get(report.response, "analysis")
    for extra in (_manipulation_section(analysis), _dates_section(analysis)):
        if extra:
            sections.append(extra)
    sections.append(CAVEAT)
    if report.demo:
        sections.append("_Tryb demonstracyjny: przykładowe dane, a nie prawdziwa weryfikacja._")
    return "\n\n".join(sections)
