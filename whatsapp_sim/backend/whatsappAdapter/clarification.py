"""Clarification loop shared by the WhatsApp bot and the website.

A vague message about a specific event ("Czy naprawdę spadł dron w Polsce?") makes the
assistant ask for details (time, place) before searching fact checks.

- ``next_step`` decides one step of the loop from the conversation so far: ask more
  questions or check a claim. Both channels use it, so they behave the same.
- WhatsApp keeps the open conversation per sender in ``ConversationStore`` until the
  user answers, skips, cancels, or the entry expires (in memory only).
- The website keeps the conversation in the browser and sends it to ``POST /api/clarify``
  with every answer, so the server stores nothing.
"""

import asyncio
import contextlib
import re
import time
import unicodedata
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from typing import Literal, Protocol

from textAnalysis.clarification import (
    MAX_QUESTIONS,
    ClarificationResult,
    DialogueTurn,
    combined_claim,
)

DEFAULT_TTL_SECONDS = 15 * 60
DEFAULT_MAX_ENTRIES = 10_000
# How many times the assistant may ask for details before it checks what it has.
MAX_CLARIFICATION_ROUNDS = 2
# Longer messages (articles, chain messages) carry enough statements to search directly.
MAX_CLARIFY_CHARS = 600
MIN_CHECK_CHARS = 8
DEFAULT_CLARIFY_TIMEOUT = 20.0


@dataclass(frozen=True)
class PendingClarification:
    """An open clarification conversation with one sender."""

    turns: tuple[DialogueTurn, ...]
    rounds: int
    understood_claim: str = ""
    resolved_claim: str = ""
    forwarded: bool = False
    frequently_forwarded: bool = False
    updated_at: float = field(default=0.0, compare=False)


class ConversationStore:
    """In-memory clarification state per sender, with expiry and a size limit.

    A shared deployment with several workers would swap this for Redis or similar;
    the bot only uses ``get``, ``put`` and ``pop``.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, PendingClarification] = OrderedDict()

    def __len__(self) -> int:
        self._expire()
        return len(self._entries)

    def _expire(self) -> None:
        deadline = self._clock() - self.ttl_seconds
        while self._entries:
            sender, entry = next(iter(self._entries.items()))
            if entry.updated_at > deadline:
                break
            del self._entries[sender]

    def get(self, sender: str) -> PendingClarification | None:
        self._expire()
        return self._entries.get(sender)

    def put(self, sender: str, pending: PendingClarification) -> None:
        self._expire()
        self._entries.pop(sender, None)
        self._entries[sender] = replace(pending, updated_at=self._clock())
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def pop(self, sender: str) -> PendingClarification | None:
        self._expire()
        return self._entries.pop(sender, None)


class Clarifier(Protocol):
    mode: str

    async def assess(
        self, turns: Sequence[DialogueTurn], *, round_index: int, max_rounds: int
    ) -> ClarificationResult: ...


Assess = Callable[..., Awaitable[ClarificationResult]]


class LiveClarifier:
    """Ask the language model (``textAnalysis.clarification``) whether to ask for details."""

    mode = "live"

    def __init__(self, assess: Assess | None = None) -> None:
        if assess is None:
            from textAnalysis.clarification import run_clarification

            assess = run_clarification
        self._assess = assess

    async def assess(
        self, turns: Sequence[DialogueTurn], *, round_index: int, max_rounds: int
    ) -> ClarificationResult:
        return await self._assess(turns, round_index=round_index, max_rounds=max_rounds)


# --- one step of the loop -----------------------------------------------------------------

# Called with the conversation and the round number; None means "no answer, go on".
AssessTurns = Callable[[Sequence[DialogueTurn], int], Awaitable[ClarificationResult | None]]


def should_clarify(text: str) -> bool:
    """Only short messages are worth asking about; links and long texts are checked as is."""

    candidate = text.strip()
    return len(candidate) <= MAX_CLARIFY_CHARS and not candidate.startswith(("http://", "https://"))


def _user_texts(turns: Sequence[DialogueTurn]) -> list[str]:
    return [turn.text for turn in turns if turn.role == "user" and turn.text.strip()]


def has_answers(turns: Sequence[DialogueTurn]) -> bool:
    """True when the user wrote anything after the first message."""

    return len(_user_texts(turns)) > 1


def skip_claim(turns: Sequence[DialogueTurn], resolved_claim: str = "") -> str:
    """What to check when the loop ends: the details given so far, or the first message."""

    if has_answers(turns):
        return resolved_claim or combined_claim(turns)
    texts = _user_texts(turns)
    return texts[0] if texts else ""


@dataclass(frozen=True)
class ClarificationStep:
    """The next move: ask (``questions``), check (``claim``) or reject a too short message."""

    action: Literal["ask", "check", "too_short"]
    # The conversation this step belongs to; a new topic starts a fresh one.
    turns: tuple[DialogueTurn, ...]
    questions: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    understood_claim: str = ""
    resolved_claim: str = ""
    claim: str = ""
    # The claim includes the user's answers (shown as "checked with your details").
    with_details: bool = False
    new_topic: bool = False

    @property
    def rounds(self) -> int:
        """Questions asked so far in ``turns``."""

        return sum(turn.role == "bot" for turn in self.turns)

    @property
    def skip_claim(self) -> str:
        return skip_claim(self.turns, self.resolved_claim)

    def question_turn(self) -> DialogueTurn:
        return DialogueTurn("bot", "\n".join(self.questions))


async def next_step(
    assess: AssessTurns,
    turns: Sequence[DialogueTurn],
    *,
    max_rounds: int = MAX_CLARIFICATION_ROUNDS,
    min_chars: int = MIN_CHECK_CHARS,
) -> ClarificationStep:
    """Decide what to do with the conversation so far (first message, questions, answers)."""

    turns = tuple(turns)
    texts = _user_texts(turns)
    if not texts:
        raise ValueError("the conversation needs a user message")
    answered = len(texts) > 1
    if not answered and not should_clarify(texts[0]):
        return ClarificationStep("check", turns, claim=texts[0])

    asked = sum(turn.role == "bot" for turn in turns)
    result = await assess(turns, asked + 1)

    if result is not None and result.new_topic and answered:
        # Not an answer but a new message: drop the old thread and start over.
        fresh = (DialogueTurn("user", texts[-1]),)
        if len(texts[-1].strip()) < min_chars:
            return ClarificationStep("too_short", fresh, new_topic=True)
        step = await next_step(assess, fresh, max_rounds=max_rounds, min_chars=min_chars)
        return replace(step, new_topic=True)

    if result is None:
        claim = skip_claim(turns, combined_claim(turns))
        return ClarificationStep("check", turns, claim=claim, with_details=answered)

    if (
        result.needs_clarification
        and result.questions
        and not result.user_declined
        and asked < max_rounds
    ):
        return ClarificationStep(
            "ask",
            turns,
            questions=tuple(result.questions),
            missing=tuple(result.missing),
            understood_claim=result.understood_claim,
            resolved_claim=result.resolved_claim,
        )
    return ClarificationStep(
        "check",
        turns,
        understood_claim=result.understood_claim,
        resolved_claim=result.resolved_claim,
        claim=skip_claim(turns, result.resolved_claim),
        with_details=answered,
    )


def guarded(
    clarifier: Clarifier,
    *,
    timeout: float = DEFAULT_CLARIFY_TIMEOUT,
    max_rounds: int = MAX_CLARIFICATION_ROUNDS,
    on_call: Callable[[], Awaitable[None]] | None = None,
    label: str = "",
) -> AssessTurns:
    """Wrap a clarifier so errors and timeouts become None: the loop never blocks a check."""

    async def assess(turns: Sequence[DialogueTurn], round_index: int) -> ClarificationResult | None:
        if on_call is not None:
            with contextlib.suppress(Exception):
                await on_call()
        try:
            async with asyncio.timeout(timeout):
                return await clarifier.assess(turns, round_index=round_index, max_rounds=max_rounds)
        except Exception as exc:  # noqa: BLE001 - clarification is optional
            print(
                f"[clarification] {label}pomijam doprecyzowanie ({type(exc).__name__}).",
                flush=True,
            )
            return None

    return assess


# --- demo ---------------------------------------------------------------------------------


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold().replace("ł", "l"))
    return "".join(char for char in decomposed if not unicodedata.combining(char))


_EVENT_STEMS = (
    "spadl",
    "spadn",
    "dron",
    "wybuch",
    "eksploz",
    "pozar",
    "zawalil",
    "zamach",
    "atak",
    "strzelanin",
    "katastrof",
    "wypadek",
    "wykolei",
    "powodz",
    "trzesienie",
    "zestrzel",
    "ewakuac",
    "zatrzyma",
    "aresztowa",
    "rakiet",
)
_TIME_PATTERN = re.compile(
    r"\b(19|20)\d{2}\b|\b\d{1,2}[./-]\d{1,2}\b|"
    r"\b(wczoraj|przedwczoraj|dzis|dzisiaj|dzisiejsz|teraz|rano|wieczor|w nocy|noc[ay]?|"
    r"godzin|temu|tydzien|tygodni|miesiac|weekend|"
    r"poniedzial|wtor|srod|czwart|piat|sobot|niedziel|"
    r"stycz|lut|marc|kwiet|maj|czerw|lip|sierp|wrzes|pazdziern|listopad|grud)",
)
_PLACE_PREPOSITIONS = {
    "w",
    "we",
    "na",
    "pod",
    "nad",
    "kolo",
    "obok",
    "niedaleko",
    "okolicach",
    "okolicy",
    "przy",
}
# Words after a preposition that do not name a concrete place.
_NOT_PLACES = {
    "polsce",
    "polska",
    "polski",
    "kraju",
    "europie",
    "swiecie",
    "sieci",
    "internecie",
    "necie",
    "mediach",
    "telewizji",
    "radiu",
    "gazecie",
    "artykule",
    "poscie",
    "facebooku",
    "tiktoku",
    "grupie",
    "wiadomosciach",
    "prawde",
    "prawda",
    "serio",
    "tym",
    "tej",
    "ten",
    "tamtym",
    "zeszlym",
    "zeszly",
    "przyszlym",
    "ostatnim",
    "ostatnia",
    "czasie",
    "trakcie",
    "ogole",
    "pewno",
    "pewnym",
}
_PLACE_WORDS = ("wojewodztw", "powiat", "gmin", "miast", "wsi", "wies", "granic", "lotnisk")
_FILLER_WORDS = {"chyba", "nie", "tak", "to", "jakos", "gdzies", "raczej", "moze", "okolo"}


def _has_place(text: str, *, answer: bool) -> bool:
    folded_words = re.findall(r"[a-z0-9]+", _fold(text))
    if any(word.startswith(_PLACE_WORDS) for word in folded_words):
        return True
    for previous, word in zip(folded_words, folded_words[1:], strict=False):
        if (
            previous in _PLACE_PREPOSITIONS
            and len(word) >= 3
            and word not in _NOT_PLACES
            and not _TIME_PATTERN.match(word)
        ):
            return True
    # A capitalized name inside the sentence ("koło Rzeszowa", "Wyryki").
    raw_words = re.findall(r"\w+", text)
    for index, word in enumerate(raw_words):
        folded = _fold(word)
        if index == 0 and not answer:
            continue
        if (
            word[:1].isupper()
            and folded not in _NOT_PLACES | _FILLER_WORDS | {"czy"}
            and not _TIME_PATTERN.match(folded)
        ):
            return True
    # A short answer with no time words is most likely the place ("rzeszow").
    return (
        answer
        and 1 <= len(folded_words) <= 3
        and not any(_TIME_PATTERN.match(word) for word in folded_words)
        and not set(folded_words) & _FILLER_WORDS
    )


_DECLINE_PATTERN = re.compile(
    r"\b(nie wiem|nie pamietam|nie mam pojecia|brak|obojetnie|bez znaczenia|nie znam)\b"
)
_DEMO_QUESTIONS = {
    "czas": "Kiedy mniej więcej to się stało (dzień, tydzień, miesiąc)?",
    "miejsce": "Gdzie to było — miasto, gmina albo region?",
}


def _strip_question(text: str) -> str:
    claim = " ".join(text.split()).rstrip("?!. ")
    claim = re.sub(
        r"^(czy\s+)?(to\s+)?(na\s*prawd[eę]|naprawd[eę]|prawda,?\s+(ze|że)|serio)\s+",
        "",
        claim,
        flags=re.IGNORECASE,
    )
    claim = re.sub(r"^czy\s+", "", claim, flags=re.IGNORECASE)
    return claim[:1].upper() + claim[1:] + "." if claim else ""


class DemoClarifier:
    """Keyword rules that mimic the model, so the loop works without API keys.

    An event word ("dron", "wybuch", "spadł"…) without a time or a concrete place
    triggers a question; the answers are appended to the claim verbatim.
    """

    mode = "demo"

    def __init__(self, *, today: Callable[[], date] | None = None) -> None:
        self._today = today or (lambda: datetime.now(UTC).date())

    async def assess(
        self, turns: Sequence[DialogueTurn], *, round_index: int, max_rounds: int
    ) -> ClarificationResult:
        user_texts = [turn.text for turn in turns if turn.role == "user" and turn.text.strip()]
        if not user_texts:
            return ClarificationResult(needs_clarification=False)
        first, answers = user_texts[0], user_texts[1:]
        latest = _fold(user_texts[-1])

        if answers and self._is_new_topic(latest):
            fresh = await self.assess(
                [DialogueTurn("user", user_texts[-1])], round_index=1, max_rounds=max_rounds
            )
            return replace(fresh, new_topic=True)

        declined = bool(answers) and bool(_DECLINE_PATTERN.search(latest))
        everything = _fold(" ".join(user_texts))
        event = any(stem in everything for stem in _EVENT_STEMS)
        has_place = _has_place(first, answer=False) or any(
            _has_place(text, answer=True) for text in answers
        )
        missing = []
        if event and not _TIME_PATTERN.search(everything):
            missing.append("czas")
        if event and not has_place:
            missing.append("miejsce")

        base = _strip_question(first) or first
        resolved = base if not answers else f"{base} Szczegóły: {'; '.join(answers)}."
        needs = bool(missing) and not declined and round_index <= max_rounds
        return ClarificationResult(
            needs_clarification=needs,
            questions=[_DEMO_QUESTIONS[code] for code in missing][:MAX_QUESTIONS] if needs else [],
            missing=missing if needs else [],
            understood_claim=base,
            resolved_claim=resolved,
            user_declined=declined,
            reasoning="Tryb demonstracyjny: reguły słów kluczowych.",
        )

    @staticmethod
    def _is_new_topic(folded: str) -> bool:
        # A full new question without any of the details that were asked for.
        return (
            folded.rstrip().endswith("?")
            and len(folded.split()) >= 4
            and not _TIME_PATTERN.search(folded)
            and not _has_place(folded, answer=False)
        )
