"""Conversation logic of the SprawdzTo WhatsApp contact."""

import asyncio
import contextlib
import re
import time
import unicodedata
import weakref
from collections.abc import Awaitable, Callable
from typing import Any

from observability import log_abstain
from textAnalysis.analysis import AnalysisConfigurationError, AnalysisError, InputSanitizer
from textAnalysis.clarification import DialogueTurn

from .admin_bridge import AdminMonitor, AdminSession
from .clarification import (
    MAX_CLARIFICATION_ROUNDS,
    MIN_CHECK_CHARS,
    ClarificationStep,
    Clarifier,
    ConversationStore,
    PendingClarification,
    guarded,
    has_answers,
    next_step,
    skip_claim,
)
from .cloud_api import (
    IncomingKind,
    IncomingMessage,
    ReplyButton,
    button_message,
    cta_url_message,
    parse_webhook,
    split_text,
    text_message,
)
from .formatting import format_report, verdict_card
from .pipeline import FactCheckPipeline, VerifiedReport
from .verified_formatting import format_verified, verified_card

BOT_NAME = "SprawdzTo"

EXAMPLES: dict[str, tuple[str, str]] = {
    "example_vaccines": ("Szczepionki a autyzm", "Czy to prawda, że szczepionki powodują autyzm?"),
    "example_5g": ("5G i koronawirus", "Sieć 5G rozprzestrzenia koronawirusa."),
}
HELP_BUTTON = ReplyButton(id="help", title="Jak to działa?")
WELCOME_BUTTONS = [
    *(ReplyButton(id=key, title=title) for key, (title, _) in EXAMPLES.items()),
    HELP_BUTTON,
]

WELCOME_TEXT = (
    f"Cześć! Jestem *{BOT_NAME}* — sprawdzam informacje, zanim je udostępnisz.\n\n"
    "Wyślij mi:\n"
    "• zdanie lub cytat, który krąży w sieci,\n"
    "• pytanie, np. _„Czy 5G szkodzi zdrowiu?”_,\n"
    "• treść podejrzanego łańcuszka.\n\n"
    "Sprawdzę ją tak samo jak strona Sprawdź.To: wyciągnę konkretne twierdzenia, "
    "poszukam ich w wiarygodnych źródłach i ocenię każde z nich."
)
WELCOME_BUTTONS_TEXT = "Chcesz zobaczyć, jak to działa na przykładzie?"

HELP_TEXT = (
    f"*Jak działa {BOT_NAME}?*\n\n"
    "To ta sama weryfikacja co na stronie Sprawdź.To, tylko w czacie.\n\n"
    "1. Model językowy analizuje Twoją wiadomość i wyciąga z niej konkretne twierdzenia. "
    "Gdy piszesz o konkretnym zdarzeniu, a brakuje szczegółów (np. kiedy i gdzie), "
    "najpierw o nie dopytam.\n"
    "2. Szukam ich w bazach redakcji fact-checkingowych, na stronach urzędów "
    "i zaufanych serwisów oraz w bazie znanej dezinformacji.\n"
    "3. Każde twierdzenie dostaje ocenę z uzasadnieniem i źródłami. "
    "Sprawdzam też, czy tekst nie gra na emocjach i czy zgadzają się daty.\n\n"
    "Treść wiadomości traktuję wyłącznie jako dane do sprawdzenia — "
    "polecenia ukryte w tekście są ignorowane.\n\n"
    "Komendy: *start* — powitanie, *pomoc* — ta wiadomość, "
    "*anuluj* — przerywa dopytywanie, *pomiń* — sprawdza bez dodatkowych szczegółów, "
    "*/clear* — wyczyść rozmowę."
)
CLEAR_TEXT = (
    "Nie mogę usunąć wiadomości z Twojego telefonu. Aby wyczyścić rozmowę, otwórz "
    "menu czatu w WhatsAppie i wybierz *Wyczyść czat*."
)
THANKS_TEXT = "Nie ma sprawy! Wyślij kolejną informację, jeśli chcesz coś sprawdzić."
TOO_SHORT_TEXT = "Napisz trochę więcej — najlepiej całe zdanie lub pytanie, które chcesz sprawdzić."
TOO_LONG_TEXT = (
    "Ta wiadomość jest za długa. Wklej fragment do "
    f"{InputSanitizer.MAX_INPUT_LENGTH:,} znaków.".replace(",", " ")
)
UNSUPPORTED_TEXT = (
    "Na razie sprawdzam tylko wiadomości tekstowe. "
    "Przepisz lub wklej treść, którą chcesz zweryfikować."
)
TIMEOUT_TEXT = "Sprawdzanie trwa zbyt długo. Spróbuj ponownie za chwilę."
NOT_CONFIGURED_TEXT = (
    "Serwer SprawdzTo nie ma skonfigurowanego modelu językowego.\n"
    "_Ustaw FREELLM_API_KEY w backend/.env albo uruchom adapter w trybie demo (--demo)._"
)
ANALYSIS_FAILED_TEXT = "Nie udało mi się przeanalizować tej wiadomości. Spróbuj ponownie za chwilę."
FORWARDED_NOTE = (
    "_To wiadomość przekazana dalej. Łańcuszki to częste źródło dezinformacji — "
    "nie przesyłaj jej dalej, dopóki nie sprawdzisz źródła._"
)
FREQUENTLY_FORWARDED_NOTE = (
    "_Ta wiadomość była przekazywana wiele razy. Im szybciej coś krąży, "
    "tym ostrożniej warto do tego podejść._"
)
GENERIC_ERROR_TEXT = "Coś poszło nie tak po mojej stronie. Spróbuj ponownie za chwilę."

URL_REFUSED_TEXT = (
    "Nie mogę otworzyć tego adresu. Wyślij publiczny link http(s) albo wklej treść wiadomości."
)

SOURCE_BUTTON_TEXT = "Otwórz źródło"
UNDERSTANDING_STATUS = "Sprawdzam, czy dobrze rozumiem, o co chodzi…"
ANALYZING_STATUS = "Analizuję tekst i wyciągam twierdzenia…"
SEARCHING_FULL_TEXT_STATUS = "Szukam Twojej wiadomości w bazach fact-checkingowych…"

CLARIFY_SKIP_BUTTON = ReplyButton(id="clarify_skip", title="Sprawdź bez tego")
CLARIFY_CANCEL_BUTTON = ReplyButton(id="clarify_cancel", title="Anuluj")
CLARIFY_HEADING = "*Chcę dobrze zrozumieć, o co chodzi.*"
CLARIFY_FOLLOW_UP_HEADING = "*Dzięki! Jeszcze jedno pytanie.*"
CLARIFY_FOOTER = (
    "_Odpowiedz własnymi słowami — wystarczy w przybliżeniu. "
    "Nie wiesz? Wybierz „Sprawdź bez tego”._"
)
CLARIFY_CANCELLED_TEXT = "Anulowane. Wyślij nową informację, gdy zechcesz coś sprawdzić."
NOTHING_PENDING_TEXT = (
    "Nie mam nic otwartego do sprawdzenia. Wyślij wiadomość, którą chcesz zweryfikować."
)
CHECKED_WITH_DETAILS = "Sprawdziłem z Twoimi szczegółami:"

# Receives a short status line while a message is being checked.
StatusCallback = Callable[[str], Awaitable[None]]


def assessing_status(count: int) -> str:
    if count <= 1:
        return "Porównuję twierdzenie ze źródłami i oceniam je…"
    return f"Porównuję {count} twierdzeń ze źródłami i oceniam je…"


def searching_status(count: int) -> str:
    if count <= 0:
        return SEARCHING_FULL_TEXT_STATUS
    if count == 1:
        return "Szukam twierdzenia w bazach fact-checkingowych…"
    return f"Szukam {count} twierdzeń w bazach fact-checkingowych…"


_GREETINGS = {
    "start",
    "menu",
    "czesc",
    "hej",
    "hejka",
    "siema",
    "witam",
    "witaj",
    "dzien dobry",
    "dobry wieczor",
    "hello",
    "hi",
    "hey",
}
_CLEAR = {"/clear", "/wyczysc", "/wyczyść"}
_HELP = {"pomoc", "help", "jak to dziala", "co umiesz", "info"}
_THANKS = ("dzieki", "dziekuje", "dzieks", "thx", "thanks", "thank you", "super dzieki")
_CANCEL = {"anuluj", "stop", "koniec", "cancel", "nie wazne", "niewazne", "zapomnij"}
# Answers that mean "I don't know the details, check it as it is".
_SKIP = {
    "pomin",
    "sprawdz",
    "sprawdz tak",
    "sprawdz bez tego",
    "sprawdz bez",
    "sprawdz teraz",
    "dalej",
    "nie wiem",
    "nie pamietam",
    "nie mam pojecia",
    "obojetnie",
    "skip",
}


def _normalize_command(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold().replace("ł", "l"))
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    ascii_text = re.sub(r"[^\w\s]", " ", ascii_text)
    return " ".join(ascii_text.split())


def clarification_body(result: ClarificationStep, *, follow_up: bool = False) -> str:
    """The question message: how the bot understood the claim and what it needs."""

    lines = [CLARIFY_FOLLOW_UP_HEADING if follow_up else CLARIFY_HEADING]
    if result.understood_claim:
        lines.append(f"_Rozumiem, że chodzi o: „{result.understood_claim[:300]}”_")
    questions = result.questions
    if len(questions) == 1:
        lines.append(questions[0])
    else:
        lines.append("Doprecyzuj, proszę:\n" + "\n".join(f"• {q}" for q in questions))
    lines.append(CLARIFY_FOOTER)
    return "\n\n".join(lines)[:1024]


class SprawdzToBot:
    """Answer WhatsApp messages by running the configured fact-check pipeline.

    With a ``clarifier`` the bot first checks whether a short message about a specific
    event is specific enough. If not, it asks for the missing details (time, place…),
    keeps the conversation in ``conversations`` and checks the claim built from the
    first message and the answers.
    """

    def __init__(
        self,
        pipeline: FactCheckPipeline,
        *,
        clarifier: Clarifier | None = None,
        conversations: ConversationStore | None = None,
        check_timeout: float | None = None,
        clarify_timeout: float = 20.0,
        max_clarification_rounds: int = MAX_CLARIFICATION_ROUNDS,
        monitor: AdminMonitor | None = None,
    ) -> None:
        self.pipeline = pipeline
        # Full verification takes minutes; the pipeline knows its own deadline.
        self.check_timeout = (
            check_timeout
            if check_timeout is not None
            else float(getattr(pipeline, "check_timeout", 90.0))
        )
        # Rejestr panelu admina: logi, blokady, luki informacyjne, alerty dezinformacji.
        self.monitor = monitor
        self.clarifier = clarifier
        self.conversations = conversations or ConversationStore()
        self.clarify_timeout = clarify_timeout
        self.max_clarification_rounds = max_clarification_rounds
        # One message per sender at a time, so an answer always sees the question it answers.
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    @property
    def mode(self) -> str:
        return self.pipeline.mode

    async def handle_webhook(
        self,
        payload: dict[str, Any],
        status: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> list[dict[str, Any]]:
        """Answer every user message in a webhook payload, in order.

        ``status(to, text)`` is awaited with progress lines while checking.
        """

        replies: list[dict[str, Any]] = []
        for message in parse_webhook(payload):

            async def notify(text: str, to: str = message.sender) -> None:
                if status is not None:
                    await status(to, text)

            replies.extend(await self.handle(message, status=notify))
        return replies

    async def handle(
        self, message: IncomingMessage, status: StatusCallback | None = None
    ) -> list[dict[str, Any]]:
        lock = self._locks.get(message.sender)
        if lock is None:
            lock = self._locks[message.sender] = asyncio.Lock()
        async with lock:
            return await self._handle(message, status)

    async def _handle(
        self, message: IncomingMessage, status: StatusCallback | None
    ) -> list[dict[str, Any]]:
        to = message.sender
        if message.kind is IncomingKind.WELCOME:
            self.conversations.pop(to)
            return self._welcome(to)
        if message.kind is IncomingKind.UNSUPPORTED:
            return [text_message(to, UNSUPPORTED_TEXT)]
        if message.kind is IncomingKind.BUTTON:
            if message.button_id == HELP_BUTTON.id:
                return [text_message(to, HELP_TEXT)]
            if message.button_id == CLARIFY_SKIP_BUTTON.id:
                pending = self.conversations.pop(to)
                if pending is None:
                    return [text_message(to, NOTHING_PENDING_TEXT)]
                return await self._check_pending(to, message, pending, status)
            if message.button_id == CLARIFY_CANCEL_BUTTON.id:
                self.conversations.pop(to)
                return [text_message(to, CLARIFY_CANCELLED_TEXT)]
            self.conversations.pop(to)
            if message.button_id in EXAMPLES:
                return await self._check(to, message, EXAMPLES[message.button_id][1], status)
            return self._welcome(to)

        if message.text.strip().casefold() in _CLEAR:
            # The simulator handles /clear itself; real WhatsApp keeps the chat on the phone.
            return [text_message(to, CLEAR_TEXT)]
        command = _normalize_command(message.text)
        if command in _GREETINGS:
            self.conversations.pop(to)
            return self._welcome(to)
        if command in _HELP:
            return [text_message(to, HELP_TEXT)]
        if command.startswith(_THANKS) and len(command) <= 30:
            self.conversations.pop(to)
            return [text_message(to, THANKS_TEXT)]

        pending = self.conversations.get(to)
        if pending is not None:
            if command in _CANCEL:
                self.conversations.pop(to)
                return [text_message(to, CLARIFY_CANCELLED_TEXT)]
            if len(message.text) > InputSanitizer.MAX_INPUT_LENGTH:
                return [text_message(to, TOO_LONG_TEXT)]
            if command in _SKIP:
                self.conversations.pop(to)
                return await self._check_pending(to, message, pending, status)
            if command:
                # Any answer counts here, even a short one like "wczoraj".
                return await self._continue(to, message, pending, status)

        if len(message.text.strip()) < MIN_CHECK_CHARS:
            return [text_message(to, TOO_SHORT_TEXT)]
        if len(message.text) > InputSanitizer.MAX_INPUT_LENGTH:
            return [text_message(to, TOO_LONG_TEXT)]
        return await self._start(to, message, status)

    def _welcome(self, to: str) -> list[dict[str, Any]]:
        return [
            text_message(to, WELCOME_TEXT),
            button_message(to, WELCOME_BUTTONS_TEXT, WELCOME_BUTTONS),
        ]

    # --- clarification loop ---------------------------------------------------------------

    def _assessor(self, message: IncomingMessage, status: StatusCallback | None):
        async def on_call() -> None:
            if status is not None:
                await status(UNDERSTANDING_STATUS)

        assert self.clarifier is not None
        return guarded(
            self.clarifier,
            timeout=self.clarify_timeout,
            max_rounds=self.max_clarification_rounds,
            on_call=on_call,
            label=f"Wiadomość {message.message_id}: ",
        )

    async def _start(
        self, to: str, message: IncomingMessage, status: StatusCallback | None
    ) -> list[dict[str, Any]]:
        """A new message: ask for details when it is too vague, otherwise check it."""

        if self.clarifier is None:
            return await self._check(to, message, message.text, status)
        step = await next_step(
            self._assessor(message, status),
            [DialogueTurn("user", message.text)],
            max_rounds=self.max_clarification_rounds,
        )
        return await self._apply(to, message, step, status, origin=None)

    async def _continue(
        self,
        to: str,
        message: IncomingMessage,
        pending: PendingClarification,
        status: StatusCallback | None,
    ) -> list[dict[str, Any]]:
        """The user answered a question: ask again, or check the completed claim."""

        step = await next_step(
            self._assessor(message, status),
            [*pending.turns, DialogueTurn("user", message.text)],
            max_rounds=self.max_clarification_rounds,
        )
        return await self._apply(to, message, step, status, origin=pending)

    async def _apply(
        self,
        to: str,
        message: IncomingMessage,
        step: ClarificationStep,
        status: StatusCallback | None,
        *,
        origin: PendingClarification | None,
    ) -> list[dict[str, Any]]:
        # Forward flags belong to the first message of the conversation.
        source = origin if origin is not None and not step.new_topic else None
        forwarded = source.forwarded if source else message.forwarded
        frequently = source.frequently_forwarded if source else message.frequently_forwarded

        if step.action == "too_short":
            self.conversations.pop(to)
            return [text_message(to, TOO_SHORT_TEXT)]
        if step.action == "ask":
            pending = PendingClarification(
                turns=(*step.turns, step.question_turn()),
                rounds=step.rounds + 1,
                understood_claim=step.understood_claim,
                resolved_claim=step.resolved_claim,
                forwarded=forwarded,
                frequently_forwarded=frequently,
            )
            self.conversations.put(to, pending)
            print(
                f"[whatsappAdapter] Wiadomość {message.message_id}: dopytuję o szczegóły "
                f"(runda {pending.rounds}, brakuje: {', '.join(step.missing) or '?'}).",
                flush=True,
            )
            body = clarification_body(step, follow_up=step.rounds > 0)
            return [button_message(to, body, [CLARIFY_SKIP_BUTTON, CLARIFY_CANCEL_BUTTON])]

        self.conversations.pop(to)
        return await self._check(
            to,
            message,
            step.claim,
            status,
            forwarded=forwarded,
            frequently_forwarded=frequently,
            understood=step.claim if step.with_details else None,
        )

    async def _check_pending(
        self,
        to: str,
        message: IncomingMessage,
        pending: PendingClarification,
        status: StatusCallback | None,
    ) -> list[dict[str, Any]]:
        """The user skipped the questions: check what the conversation has so far."""

        claim = skip_claim(pending.turns, pending.resolved_claim)
        return await self._check(
            to,
            message,
            claim,
            status,
            forwarded=pending.forwarded,
            frequently_forwarded=pending.frequently_forwarded,
            understood=claim if has_answers(pending.turns) else None,
        )

    # --- fact check -----------------------------------------------------------------------

    async def _check(
        self,
        to: str,
        message: IncomingMessage,
        text: str,
        status: StatusCallback | None = None,
        *,
        forwarded: bool | None = None,
        frequently_forwarded: bool | None = None,
        understood: str | None = None,
    ) -> list[dict[str, Any]]:
        if forwarded is None:
            forwarded = message.forwarded
        if frequently_forwarded is None:
            frequently_forwarded = message.frequently_forwarded
        started_at = time.perf_counter()
        # Log only identifiers and timings; message text stays out of the console.
        print(
            f"[whatsappAdapter] Wiadomość {message.message_id}: sprawdzam "
            f"({len(text)} znaków, tryb {self.mode})...",
            flush=True,
        )

        async def notify(line: str) -> None:
            if status is None:
                return
            # Progress is best effort; a lost client must not break the check.
            with contextlib.suppress(Exception):
                await status(line)

        async def on_progress(stage: str, count: int) -> None:
            if stage == "searching":
                await notify(searching_status(count))
            elif stage == "assessing":
                await notify(assessing_status(count))

        admin = AdminSession(self.monitor)
        refusal = admin.screen(to, text)
        if refusal is not None:
            print(
                f"[whatsappAdapter] Wiadomość {message.message_id}: odrzucona przez monitor.",
                flush=True,
            )
            return [text_message(to, refusal)]

        card = None
        report = None
        failure: str | None = None
        try:
            async with asyncio.timeout(self.check_timeout):
                await notify(ANALYZING_STATUS)
                report = await self.pipeline.check(text, progress=on_progress)
            if isinstance(report, VerifiedReport):
                card = verified_card(report)
                body = format_verified(report, headline=card is None)
            else:
                card = verdict_card(report)
                body = format_report(report, headline=card is None)
            if understood:
                body = f"{CHECKED_WITH_DETAILS} _„{understood[:600]}”_\n\n{body}"
            info_gap = admin.complete(report)
            if info_gap:
                body = f"{body}\n\n{info_gap}"
            if frequently_forwarded:
                body = f"{body}\n\n{FREQUENTLY_FORWARDED_NOTE}"
            elif forwarded:
                body = f"{body}\n\n{FORWARDED_NOTE}"
        except TimeoutError:
            log_abstain("timeout", channel="whatsapp", timeout_s=self.check_timeout)
            body = TIMEOUT_TEXT
            failure = "timeout"
        except AnalysisConfigurationError:
            log_abstain("not_configured", channel="whatsapp")
            body = NOT_CONFIGURED_TEXT
            failure = "not_configured"
        except AnalysisError:
            log_abstain("analysis_failed", channel="whatsapp")
            body = ANALYSIS_FAILED_TEXT
            failure = "analysis_failed"
        except Exception as exc:  # noqa: BLE001 - the chat must always get an answer
            body, failure = _verification_failure(exc)
        if failure is not None:
            admin.complete(error=failure)
        print(
            f"[whatsappAdapter] Wiadomość {message.message_id}: odpowiedź po "
            f"{time.perf_counter() - started_at:.1f}s.",
            flush=True,
        )
        replies = [text_message(to, chunk) for chunk in split_text(body)]
        if card is not None:
            replies.insert(
                0,
                cta_url_message(
                    to,
                    header=card.header,
                    body=card.body,
                    footer=card.footer,
                    display_text=SOURCE_BUTTON_TEXT,
                    url=card.url,
                ),
            )
        return replies


def _verification_failure(exc: Exception) -> tuple[str, str]:
    """Reply and admin error code for a failure, the same cases as ``/api/check``."""
    name = type(exc).__name__
    if name == "ApiFailure":  # api_routes: URL rejected, or the deadline passed
        code = str(getattr(exc, "code", "api_failure"))
        if code == "analysis_timeout":
            log_abstain("timeout", channel="whatsapp")
            return TIMEOUT_TEXT, "timeout"
        log_abstain("url_refused", channel="whatsapp", error=code)
        return URL_REFUSED_TEXT, f"url:{code}"
    if name in {"VerificationFailed", "InvalidVerificationResult"}:  # api_adapter
        kind = str(getattr(exc, "kind", name))
        log_abstain("analysis_failed", channel="whatsapp", error=kind)
        if kind.lower() == "timeout":
            return TIMEOUT_TEXT, "timeout"
        if kind == "AnalysisConfigurationError":
            return NOT_CONFIGURED_TEXT, "not_configured"
        return ANALYSIS_FAILED_TEXT, f"analysis_failed:{getattr(exc, 'part', name)}"
    print(f"[whatsappAdapter] Błąd: {name}.", flush=True)
    log_abstain("pipeline_error", channel="whatsapp", error=name)
    return GENERIC_ERROR_TEXT, f"pipeline_error:{name}"
