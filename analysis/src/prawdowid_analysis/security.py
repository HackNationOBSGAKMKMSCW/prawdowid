"""Ochrona przed prompt injection po stronie kodu (niezależna od posłuszeństwa modelu).

Warstwy:
1. `clean_text`: normalizacja NFKC (znaczniki pełnej szerokości „＜source＞”
   stają się zwykłymi „<source>”, więc da się je wykryć i zneutralizować),
   usunięcie znaków zerowej szerokości, sterujących kierunkiem tekstu i znaków
   kontrolnych, limit długości.
2. `detect_injection`: heurystyczne wykrywanie poleceń skierowanych do modelu,
   udawanych komunikatów systemowych, prób wycieku instrukcji, podszywania się
   pod znaczniki promptu i gotowych odpowiedzi JSON. Działa na tekście bez
   polskich znaków i małymi literami, po polsku i po angielsku.
3. `screen_sources`: źródło z wykrytym wstrzyknięciem trafia do KWARANTANNY –
   nie jest pokazywane modelowi i nie może być dowodem. Wynik raportuje je
   jawnie (`quarantined_sources`), więc użytkownik widzi, co i dlaczego pominięto.

Twierdzenia użytkownika nie są odrzucane (to one są przedmiotem oceny), tylko
oznaczane: model dostaje dodatkowe ostrzeżenie, a wynik zawiera
`security_warnings`. Pozostałe warstwy to neutralizacja znaczników i reguła R3
w prompcie, identyfikator-pułapka (canary) oraz weryfikacja dosłowności cytatów.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from .schemas import QuarantinedSource, ReferenceSource

MAX_CLAIM_CHARS = 1_500
MAX_SOURCE_CHARS = 50_000

# Znaki niewidoczne i sterujące kierunkiem tekstu (ukrywanie treści przed człowiekiem).
_INVISIBLE_RE = re.compile("[­᠎​-‏‪-‮⁠-⁤⁦-⁩﻿]")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# Wzorce na tekście „złożonym”: małe litery, bez diakrytyków (ł -> l).
_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "polecenie zignorowania instrukcji",
        # tryb rozkazujący (np. „zignoruj”), nie opis („rząd zignorował”)
        r"\b(zignoruj|ignoruj|pomin|zapomnij|ignore|disregard|forget)\b.{0,40}"
        r"\b(instrukc|polecen|zasad|regul|ocen|wczesniejsz|poprzedni|previous|prior|above|"
        r"instruction|rule|prompt)",
    ),
    (
        "narzucanie werdyktu",
        # tryb rozkazujący (np. „oceń”, „uznaj”), nie opis („ocenili jako fałszywe”)
        r"\b(ocen|oceniaj|uznaj|uznawaj|oznacz|zwroc|odpowiedz|zaklasyfikuj|potraktuj|"
        r"evaluate|rate|mark|classify|return|answer|treat)\b"
        r".{0,60}\b(jako|za|as|with)\b.{0,20}\b(prawd|falsz|true|false|verdict|werdykt)",
    ),
    ("odwołanie do werdyktu w JSON", r"[\"']?\b(verdict|werdykt|confidence)\b[\"']?\s*:\s*[\"']"),
    (
        "zwrot do modelu",
        r"\b(uwaga|wiadomosc|instrukcja|note|message)\s+(dla|do|for|to)\s+"
        r"(modelu|asystenta|ai|sztucznej|llm|model|assistant|chatbota)\b",
    ),
    (
        "zwrot do asystenta",
        r"\b(asystencie|drogi modelu|dear (assistant|model)|hey (assistant|chatgpt))\b",
    ),
    (
        "zmiana roli",
        r"\b(jestes teraz|od teraz jestes|you are now|act as|udawaj ze|pretend to be)\b",
    ),
    (
        "udawany komunikat systemowy",
        r"(^|\n)\s*\[?\s*(system|assistant|developer|asystent)\s*\]?\s*[:\]]|\[\s*system\s*\]|"
        r"<\|im_(start|end)\|>|#{2,}\s*(system|instruction|instrukcja)",
    ),
    (
        "próba wycieku instrukcji",
        r"\b(wypisz|przepisz|ujawnij|pokaz|podaj|reveal|print|show|repeat|output)\w*\b.{0,60}"
        r"\b(instrukcj|prompt|polecen\w* systemow|system prompt|instructions)",
    ),
    (
        "podszywanie się pod znaczniki promptu",
        r"<\s*/?\s*(claim|source|context|system|user|assistant|untrusted_text)\b",
    ),
    (
        "podważanie innych źródeł",
        r"\b(pozostale|inne|wszystkie inne|other|all other)\s+(zrodla|sources)\b.{0,60}"
        r"\b(nieaktualn|pomin|zignoruj|falszyw|ignore|outdated|unreliable|niewiarygodn)",
    ),
    (
        "deklaracja jedynego wiarygodnego źródła",
        r"\b(jedynym wiarygodnym|only (reliable|trustworthy|valid) source)\b",
    ),
)
_COMPILED = tuple(
    (label, re.compile(pattern, re.IGNORECASE | re.DOTALL)) for label, pattern in _PATTERNS
)


def clean_text(text: str, max_chars: int | None = None) -> str:
    """Normalizuje tekst: NFKC, bez znaków niewidocznych i kontrolnych, z limitem długości."""
    cleaned = unicodedata.normalize("NFKC", text or "")
    cleaned = _INVISIBLE_RE.sub(" ", cleaned)
    cleaned = _CONTROL_RE.sub("", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    if max_chars is not None and len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]
    return cleaned.strip()


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower().replace("ł", "l"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def detect_injection(text: str) -> list[str]:
    """Zwraca listę wykrytych typów manipulacji (pusta = nic nie wykryto)."""
    folded = _fold(clean_text(text))
    return [label for label, pattern in _COMPILED if pattern.search(folded)]


@dataclass
class ScreenedClaim:
    text: str
    warnings: list[str]


def screen_claim(claim: str) -> ScreenedClaim:
    warnings = []
    cleaned = clean_text(claim, MAX_CLAIM_CHARS)
    if len(clean_text(claim)) > MAX_CLAIM_CHARS:
        warnings.append(f"Twierdzenie skrócono do {MAX_CLAIM_CHARS} znaków.")
    findings = detect_injection(claim)
    if findings:
        warnings.append(
            "Twierdzenie zawiera tekst przypominający polecenia dla modelu ("
            + ", ".join(findings)
            + "); oceniana jest wyłącznie jego treść faktograficzna."
        )
    return ScreenedClaim(text=cleaned, warnings=warnings)


def screen_sources(
    sources: Iterable[ReferenceSource],
) -> tuple[list[ReferenceSource], list[QuarantinedSource]]:
    """Czyści źródła i odkłada do kwarantanny te, które zawierają wstrzyknięcia."""
    clean: list[ReferenceSource] = []
    quarantined: list[QuarantinedSource] = []
    for source in sources:
        findings = detect_injection(f"{source.title}\n{source.text}")
        if findings:
            quarantined.append(
                QuarantinedSource(
                    source_id=source.source_id,
                    kind=source.kind,
                    title=source.title,
                    publisher=source.publisher,
                    url=source.url,
                    reasons=findings,
                )
            )
            continue
        text = clean_text(source.text, MAX_SOURCE_CHARS)
        if not text:
            continue
        clean.append(
            source.model_copy(update={"text": text, "title": clean_text(source.title, 300)})
        )
    return clean, quarantined
