"""Grupowanie twierdzeń w tematy, żeby liczyć, ilu różnych użytkowników pyta o to samo.

Twierdzenie jest sprowadzane do zbioru rdzeni słów (bez polskich znaków, bez słów
funkcyjnych, przycięte do kilku liter, co łagodzi odmianę). Dwa twierdzenia należą do
tego samego tematu, gdy ich zbiory są dostatecznie podobne (indeks Jaccarda).
"""

from __future__ import annotations

import re
import unicodedata

STEM_LENGTH = 6
SIMILARITY_THRESHOLD = 0.6

_TRANSLITERATION = str.maketrans({"ł": "l", "Ł": "L", "ß": "ss"})

# textAnalysis formułuje stwierdzenia jako „Tekst zawiera twierdzenie, że …”.
_REPORTING_PREFIX = re.compile(
    r"^(?:(?:ten|w)\s+)?(?:tekst|autor|wpis|artykul|post|wiadomosc|uzytkownik)\w*\s+"
    r"(?:zawiera|przedstawia|podaje|twierdzi|sugeruje|stwierdza|glosi)\w*\s+"
    r"(?:(?:twierdzenie|informacje|teze)\s+)?(?:ze|iz)\s+"
)

_STOPWORDS_TEXT = """
    a aby ale albo bo by byc byl byla bylo byly co czy dla do gdy gdzie i ich ile im iz
    ja jak jako jaki jakie je jego jej jest jestem jesli juz ktora ktore ktory ktorzy ma
    maja mi mnie na nad nas nie nich nim niz o od oraz po pod przez przy sa sie ta tak
    takze tam te tego tej ten to tu tutaj tym u w we wiec wszystko z za ze zostal zostala
    zostalo zostaly prawda czyli rowniez jednak tylko bardzo moze mozna tez
    the an and or of to in on at is are was were be been it that this for with as by
    from not do does did has have had which who what rok roku
"""
STOPWORDS = frozenset(_STOPWORDS_TEXT.split())


def normalize(text: str) -> str:
    """Małe litery, bez znaków diakrytycznych i bez prefiksu relacjonującego."""
    folded = unicodedata.normalize("NFKD", text.translate(_TRANSLITERATION))
    plain = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    plain = re.sub(r"[^\w\s%,.-]", " ", plain)
    plain = re.sub(r"[,.](?=\s|$)", " ", plain)  # interpunkcja, ale nie 77,45 ani 3.5
    plain = re.sub(r"\s+", " ", plain).strip()
    previous = None
    while previous != plain:  # „Tekst zawiera twierdzenie, że autor twierdzi, że …”
        previous = plain
        plain = _REPORTING_PREFIX.sub("", plain).strip()
    return plain


def tokens(text: str) -> frozenset[str]:
    """Zbiór rdzeni słów znaczących; liczby zostają w całości."""
    words = re.findall(r"[a-z]+|\d+(?:[.,]\d+)?", normalize(text))
    stems = set()
    for word in words:
        if word in STOPWORDS:
            continue
        if word[0].isdigit():
            stems.add(word.replace(",", "."))
        elif len(word) > 1:
            stems.add(word[:STEM_LENGTH])
    return frozenset(stems)


def similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    if min(len(left), len(right)) < 3:  # krótkie twierdzenia: tylko identyczne
        return 1.0 if left == right else 0.0
    return len(left & right) / len(left | right)


def same_topic(left: frozenset[str], right: frozenset[str]) -> bool:
    return similarity(left, right) >= SIMILARITY_THRESHOLD
