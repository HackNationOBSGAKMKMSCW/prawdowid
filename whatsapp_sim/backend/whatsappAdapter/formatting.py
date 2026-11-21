"""Turn a fact-check report into a WhatsApp-formatted reply.

WhatsApp markup: ``*bold*``, ``_italic_``, ``~strike~`` and ``` ```mono``` ```.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from apiReading.exceptions import ApiAuthError
from apiReading.models import ReadingResult

from .cloud_api import MAX_HEADER_CHARS, MAX_INTERACTIVE_BODY_CHARS
from .pipeline import CheckReport
from .verdicts import OverallVerdict, Verdict, classify_rating, overall_verdict

MAX_CLAIMS_PER_STATEMENT = 3
MAX_REVIEWS_PER_CLAIM = 2

_OVERALL_HEADLINES = {
    OverallVerdict.FALSE: "*Prawdopodobnie FAŁSZ*",
    OverallVerdict.MISLEADING: "*Wprowadza w błąd lub jest tylko częściowo prawdziwe*",
    OverallVerdict.TRUE: "*Prawdopodobnie PRAWDA*",
    OverallVerdict.CONFLICTING: "*Oceny są rozbieżne*",
    OverallVerdict.UNVERIFIED: "*Brak jednoznacznej oceny*",
    OverallVerdict.NO_DATA: "*Nie znalazłem weryfikacji*",
}

# Plain-text card headers (interactive headers do not support markup).
_CARD_HEADERS = {
    OverallVerdict.FALSE: "Prawdopodobnie FAŁSZ",
    OverallVerdict.MISLEADING: "Wprowadza w błąd",
    OverallVerdict.TRUE: "Prawdopodobnie PRAWDA",
    OverallVerdict.CONFLICTING: "Oceny są rozbieżne",
    OverallVerdict.UNVERIFIED: "Brak jednoznacznej oceny",
}
_OVERALL_TO_VERDICT = {
    OverallVerdict.FALSE: Verdict.FALSE,
    OverallVerdict.MISLEADING: Verdict.MISLEADING,
    OverallVerdict.TRUE: Verdict.TRUE,
}

_NO_DATA_TIPS = (
    "*Co możesz zrobić:*\n"
    "• sprawdź, kto jest autorem i gdzie to opublikowano,\n"
    "• poszukaj tej informacji w kilku niezależnych źródłach,\n"
    "• uważaj na nagłówki, które mocno grają na emocjach."
)


@dataclass(frozen=True)
class _Review:
    verdict: Verdict
    rating: str
    publisher: str
    date: str
    url: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.url, self.publisher, self.rating)


def _clip(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _format_date(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%d.%m.%Y")
    except ValueError:
        return ""


def _safe_url(value: Any) -> str:
    return value if isinstance(value, str) and value.startswith(("https://", "http://")) else ""


def _reviews_of(payload: dict[str, Any]) -> list[_Review]:
    reviews = []
    for review in payload.get("claimReview") or []:
        if not isinstance(review, dict):
            continue
        publisher = review.get("publisher") or {}
        rating = _clip(review.get("textualRating"), 60)
        reviews.append(
            _Review(
                verdict=classify_rating(rating),
                rating=rating or "bez oceny",
                publisher=_clip(publisher.get("name") or publisher.get("site"), 60)
                or "nieznany wydawca",
                date=_format_date(review.get("reviewDate")),
                url=_safe_url(review.get("url")),
            )
        )
    return reviews


def _review_lines(review: _Review) -> list[str]:
    meta = " · ".join(part for part in (review.publisher, review.date) if part)
    lines = [f"*{review.rating}* · {meta}"]
    if review.url:
        lines.append(review.url)
    return lines


def _result_failed(result: ReadingResult) -> bool:
    return bool(result.results) and all(outcome.error is not None for outcome in result.results)


def _claim_blocks(result: ReadingResult) -> list[str]:
    blocks = []
    for item in result.items[:MAX_CLAIMS_PER_STATEMENT]:
        lines = []
        claim = _clip(item.payload.get("text"), 160)
        if claim:
            claimant = _clip(item.payload.get("claimant"), 60)
            lines.append(f"↳ „{claim}”" + (f" — {claimant}" if claimant else ""))
        for review in _reviews_of(item.payload)[:MAX_REVIEWS_PER_CLAIM]:
            lines.extend(_review_lines(review))
        if lines:
            blocks.append("\n".join(lines))
    return blocks


def _missing_key(report: CheckReport) -> bool:
    return any(
        isinstance(outcome.error, ApiAuthError)
        for result in report.results
        for outcome in result.results
    )


@dataclass(frozen=True)
class VerdictCard:
    """Headline verdict with the most relevant source, sent as a link card."""

    header: str
    body: str
    footer: str
    url: str


def _all_reviews(report: CheckReport) -> dict[tuple[str, str, str], _Review]:
    return {
        review.key: review
        for result in report.results
        for item in result.items
        for review in _reviews_of(item.payload)
    }


def _reviews_word(count: int) -> str:
    """Polish plural of "weryfikacja" for a count (1, 2-4, 5+)."""

    if count == 1:
        return "weryfikacja"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "weryfikacje"
    return "weryfikacji"


def verdict_card(report: CheckReport) -> VerdictCard | None:
    """Summarize the verdict as a card, or None when there is no linked review."""

    reviews = _all_reviews(report)
    overall = overall_verdict(review.verdict for review in reviews.values())
    if overall not in _CARD_HEADERS:
        return None

    wanted = _OVERALL_TO_VERDICT.get(overall)
    candidates = []
    for result in report.results:
        for item in result.items:
            subject = item.payload.get("text") if report.searched_full_text else None
            subject = subject or result.request.query
            for review in _reviews_of(item.payload):
                if review.url:
                    candidates.append((subject, review))
    if not candidates:
        return None
    subject, top = next(
        ((subject, review) for subject, review in candidates if review.verdict is wanted),
        candidates[0],
    )

    meta = " · ".join(part for part in (top.publisher, top.date) if part)
    body = f"_„{_clip(subject, 300)}”_\n\n*{top.rating}* — {meta}"
    count = len(reviews)
    footer = f"SprawdzTo · {count} {_reviews_word(count)}"
    if report.demo:
        footer += " · dane demo"
    return VerdictCard(
        header=_CARD_HEADERS[overall][:MAX_HEADER_CHARS],
        body=body[:MAX_INTERACTIVE_BODY_CHARS],
        footer=footer,
        url=top.url,
    )


def format_report(report: CheckReport, *, headline: bool = True) -> str:
    """Render the full reply: overall verdict, evidence per statement, caveats.

    With ``headline=False`` the verdict lines are left out because a
    ``verdict_card`` already shows them.
    """

    results = report.results
    all_reviews = _all_reviews(report)
    failed = [result for result in results if _result_failed(result)]
    footer: list[str] = []

    if results and len(failed) == len(results):
        sections = [
            "*Nie udało się sprawdzić*",
            "_Baza weryfikacji jest teraz niedostępna. Spróbuj ponownie za chwilę._",
        ]
        if _missing_key(report):
            sections.append("_(Serwer nie ma ustawionego klucza GOOGLE_FACT_CHECK_API_KEY.)_")
        return _with_notes("\n\n".join(sections), report)

    overall = overall_verdict(review.verdict for review in all_reviews.values())
    sections = ["*Wynik sprawdzenia*", _OVERALL_HEADLINES[overall]]
    publishers = sorted({review.publisher for review in all_reviews.values()})
    if not headline:
        sections = ["*Szczegóły sprawdzenia*"]
    elif overall is OverallVerdict.NO_DATA:
        sections[-1] += (
            "\n_Nie ma tego w bazach redakcji fact-checkingowych. To nie znaczy, "
            "że informacja jest prawdziwa ani że jest fałszywa._"
        )
    else:
        basis = f"_Na podstawie {len(all_reviews)} weryfikacji: {', '.join(publishers[:4])}"
        basis += " i innych._" if len(publishers) > 4 else "._"
        if overall is OverallVerdict.CONFLICTING:
            basis += "\n_Redakcje różnie oceniają podobne twierdzenia — przeczytaj uzasadnienia._"
        sections[-1] += "\n" + basis

    if report.analysis.category:
        sections.append(f"Temat: {report.analysis.category}")

    if report.searched_full_text:
        blocks = _claim_blocks(results[0]) if results else []
        if blocks:
            sections.append("*Znalezione weryfikacje dla Twojej wiadomości:*")
            sections.extend(blocks)
        if results and results[0].request.metadata.get("truncated"):
            footer.append("_Wiadomość była długa — przeszukałem jej pierwsze 1000 znaków._")
    else:
        for index, result in enumerate(results, 1):
            heading = f"*{index}.* _„{_clip(result.request.query, 200)}”_"
            if _result_failed(result):
                sections.append(f"{heading}\nNie udało się sprawdzić tego twierdzenia.")
                continue
            blocks = _claim_blocks(result)
            if not blocks:
                sections.append(f"{heading}\nBrak weryfikacji tego twierdzenia.")
                continue
            sections.append("\n".join([heading, *blocks]))

    if failed:
        footer.append("_Części zapytań nie udało się wykonać — wynik może być niepełny._")
    if all_reviews:
        footer.append(
            "_Weryfikacje mogą dotyczyć podobnych, a nie identycznych twierdzeń. "
            "Zanim coś udostępnisz, otwórz link i przeczytaj uzasadnienie._"
        )
    else:
        footer.append(_NO_DATA_TIPS)

    return _with_notes("\n\n".join(sections + footer), report)


def _with_notes(body: str, report: CheckReport) -> str:
    notes = []
    if report.analysis.security_warnings:
        notes.append(
            "_Wiadomość zawierała fragmenty przypominające polecenia dla bota. "
            "Potraktowałem je wyłącznie jako tekst do sprawdzenia._"
        )
    if report.demo:
        notes.append("_Tryb demonstracyjny: przykładowe dane, a nie prawdziwa weryfikacja._")
    return "\n\n".join([body, *notes])
