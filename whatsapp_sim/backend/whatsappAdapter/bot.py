"""Conversation logic of the SprawdzTo WhatsApp contact."""

import asyncio
import re
import time
import unicodedata
from typing import Any

from textAnalysis.analysis import AnalysisConfigurationError, AnalysisError, InputSanitizer

from .cloud_api import (
    IncomingKind,
    IncomingMessage,
    ReplyButton,
    button_message,
    parse_webhook,
    split_text,
    text_message,
)
from .formatting import format_report
from .pipeline import FactCheckPipeline

BOT_NAME = "SprawdzTo"
MIN_CHECK_CHARS = 8

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
    f"👋 Cześć! Jestem *{BOT_NAME}* — sprawdzam informacje, zanim je udostępnisz.\n\n"
    "Wyślij mi:\n"
    "• zdanie lub cytat, który krąży w sieci,\n"
    "• pytanie, np. _„Czy 5G szkodzi zdrowiu?”_,\n"
    "• treść podejrzanego łańcuszka.\n\n"
    "Wyciągnę z tekstu konkretne twierdzenia i poszukam ich w bazach "
    "niezależnych redakcji fact-checkingowych."
)
WELCOME_BUTTONS_TEXT = "Chcesz zobaczyć, jak to działa na przykładzie?"

HELP_TEXT = (
    f"ℹ️ *Jak działa {BOT_NAME}?*\n\n"
    "1️⃣ Model językowy analizuje Twoją wiadomość: rozpoznaje temat i język "
    "i wyciąga z niej konkretne twierdzenia.\n"
    "2️⃣ Każde twierdzenie wyszukuję w Google Fact Check Tools — bazie weryfikacji "
    "publikowanych przez redakcje fact-checkingowe z całego świata.\n"
    "3️⃣ Zbieram ich oceny w jeden werdykt i podaję linki do źródeł.\n\n"
    "🛡️ Treść wiadomości traktuję wyłącznie jako dane do sprawdzenia — "
    "polecenia ukryte w tekście są ignorowane.\n\n"
    "Komendy: *start* — powitanie, *pomoc* — ta wiadomość."
)
THANKS_TEXT = "Nie ma sprawy! 🙌 Wyślij kolejną informację, jeśli chcesz coś sprawdzić."
TOO_SHORT_TEXT = (
    "✍️ Napisz trochę więcej — najlepiej całe zdanie lub pytanie, które chcesz sprawdzić."
)
TOO_LONG_TEXT = (
    "✂️ Ta wiadomość jest za długa. Wklej fragment do "
    f"{InputSanitizer.MAX_INPUT_LENGTH:,} znaków.".replace(",", " ")
)
UNSUPPORTED_TEXT = (
    "📎 Na razie sprawdzam tylko wiadomości tekstowe. "
    "Przepisz lub wklej treść, którą chcesz zweryfikować."
)
TIMEOUT_TEXT = "⏱️ Sprawdzanie trwa zbyt długo. Spróbuj ponownie za chwilę."
NOT_CONFIGURED_TEXT = (
    "⚠️ Serwer SprawdzTo nie ma skonfigurowanego modelu językowego.\n"
    "_Ustaw FREELLM_API_KEY w backend/.env albo uruchom adapter w trybie demo (--demo)._"
)
ANALYSIS_FAILED_TEXT = (
    "😕 Nie udało mi się przeanalizować tej wiadomości. Spróbuj ponownie za chwilę."
)
FORWARDED_NOTE = (
    "↪️ _To wiadomość przekazana dalej. Łańcuszki to częste źródło dezinformacji — "
    "nie przesyłaj jej dalej, dopóki nie sprawdzisz źródła._"
)
FREQUENTLY_FORWARDED_NOTE = (
    "⏩ _Ta wiadomość była przekazywana wiele razy. Im szybciej coś krąży, "
    "tym ostrożniej warto do tego podejść._"
)
GENERIC_ERROR_TEXT = "😕 Coś poszło nie tak po mojej stronie. Spróbuj ponownie za chwilę."

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
_HELP = {"pomoc", "help", "jak to dziala", "co umiesz", "info"}
_THANKS = ("dzieki", "dziekuje", "dzieks", "thx", "thanks", "thank you", "super dzieki")


def _normalize_command(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold().replace("ł", "l"))
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    ascii_text = re.sub(r"[^\w\s]", " ", ascii_text)
    return " ".join(ascii_text.split())


class SprawdzToBot:
    """Answer WhatsApp messages by running the configured fact-check pipeline."""

    def __init__(self, pipeline: FactCheckPipeline, *, check_timeout: float = 90.0) -> None:
        self.pipeline = pipeline
        self.check_timeout = check_timeout

    @property
    def mode(self) -> str:
        return self.pipeline.mode

    async def handle_webhook(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Answer every user message in a webhook payload, in order."""

        replies: list[dict[str, Any]] = []
        for message in parse_webhook(payload):
            replies.extend(await self.handle(message))
        return replies

    async def handle(self, message: IncomingMessage) -> list[dict[str, Any]]:
        to = message.sender
        if message.kind is IncomingKind.WELCOME:
            return self._welcome(to)
        if message.kind is IncomingKind.UNSUPPORTED:
            return [text_message(to, UNSUPPORTED_TEXT)]
        if message.kind is IncomingKind.BUTTON:
            if message.button_id == HELP_BUTTON.id:
                return [text_message(to, HELP_TEXT)]
            if message.button_id in EXAMPLES:
                return await self._check(to, message, EXAMPLES[message.button_id][1])
            return self._welcome(to)

        command = _normalize_command(message.text)
        if command in _GREETINGS:
            return self._welcome(to)
        if command in _HELP:
            return [text_message(to, HELP_TEXT)]
        if command.startswith(_THANKS) and len(command) <= 30:
            return [text_message(to, THANKS_TEXT)]
        if len(message.text.strip()) < MIN_CHECK_CHARS:
            return [text_message(to, TOO_SHORT_TEXT)]
        if len(message.text) > InputSanitizer.MAX_INPUT_LENGTH:
            return [text_message(to, TOO_LONG_TEXT)]
        return await self._check(to, message, message.text)

    def _welcome(self, to: str) -> list[dict[str, Any]]:
        return [
            text_message(to, WELCOME_TEXT),
            button_message(to, WELCOME_BUTTONS_TEXT, WELCOME_BUTTONS),
        ]

    async def _check(self, to: str, message: IncomingMessage, text: str) -> list[dict[str, Any]]:
        started_at = time.perf_counter()
        # Log only identifiers and timings; message text stays out of the console.
        print(
            f"[whatsappAdapter] Wiadomość {message.message_id}: sprawdzam "
            f"({len(text)} znaków, tryb {self.mode})...",
            flush=True,
        )
        try:
            async with asyncio.timeout(self.check_timeout):
                report = await self.pipeline.check(text)
            body = format_report(report)
            if message.frequently_forwarded:
                body = f"{body}\n\n{FREQUENTLY_FORWARDED_NOTE}"
            elif message.forwarded:
                body = f"{body}\n\n{FORWARDED_NOTE}"
        except TimeoutError:
            body = TIMEOUT_TEXT
        except AnalysisConfigurationError:
            body = NOT_CONFIGURED_TEXT
        except AnalysisError:
            body = ANALYSIS_FAILED_TEXT
        except Exception as exc:  # noqa: BLE001 - the chat must always get an answer
            print(f"[whatsappAdapter] Błąd: {type(exc).__name__}.", flush=True)
            body = GENERIC_ERROR_TEXT
        print(
            f"[whatsappAdapter] Wiadomość {message.message_id}: odpowiedź po "
            f"{time.perf_counter() - started_at:.1f}s.",
            flush=True,
        )
        return [text_message(to, chunk) for chunk in split_text(body)]
