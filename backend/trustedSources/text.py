"""Language-light text normalization for matching Polish (and English) queries."""

import re
import unicodedata
from urllib.parse import unquote, urlsplit

_FOLD = str.maketrans({"ł": "l", "Ł": "l", "ß": "ss"})
_TOKEN = re.compile(r"[a-z0-9]+")
STEM_LENGTH = 7
MIN_STEM = 3
# Folded (diacritic-free) Polish inflection endings, longest first.
_SUFFIXES = tuple(
    sorted(
        """
        owego owemu owych owymi iego iemu ich ymi imi ami ach ach iej ego emu owi om ow
        ie ia iu ii ej em um a e i o u y
        """.split(),  # noqa: SIM905 - readable word list
        key=len,
        reverse=True,
    )
)

STOPWORDS = frozenset(
    """
    a aby ale albo ani az bo by byc byl byla bylo byly co czy dla do gdy gdzie go i ich ile
    im ja jak jaki jest jesli jej jego juz ktora ktore ktory ktorzy lub ma mi mnie moze na nad
    nam nas nie nic niz o od oraz po pod przez przy sa se sie siebie sobie ta tak tam te tego
    tej ten to tu tym u w we wiec wszystko z za ze zeby
    przed przez bedzie beda wszyscy wszystkie wszystkich kazdy jestem jestesmy sie zostal zostala
    about an and are as at be by for from has have in is it its not of on or that the this
    to was were will with
    html htm php aspx www pl web gov
    """.split()  # noqa: SIM905 - readable word list
)


def fold(text: str) -> str:
    """Lowercase and strip diacritics (``Płaska Ziemia`` -> ``plaska ziemia``)."""

    decomposed = unicodedata.normalize("NFKD", text.translate(_FOLD).lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def stem(token: str) -> str:
    """Light Polish stemmer: drop one inflection suffix, then keep a 7-letter prefix.

    Merges ziemia/ziemi, plaska/plaskiej, szczepionki/szczepien, autyzm/autyzmu
    while keeping szczepionki apart from Szczecinie and Szczepański.
    """

    if token.isdigit():
        return token
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= MIN_STEM:
            token = token[: -len(suffix)]
            break
    return token[:STEM_LENGTH]


def tokens(text: str) -> list[str]:
    return [token for token in _TOKEN.findall(fold(text)) if token not in STOPWORDS]


def stems(text: str) -> list[str]:
    return [stem(token) for token in tokens(text) if len(token) > 1 or token.isdigit()]


def url_words(url: str) -> str:
    """Words from a URL path slug (``/fake_news/ziemia-jest-plaska`` -> ``fake news ziemia jest plaska``)."""

    try:
        path = unquote(urlsplit(url).path)
    except ValueError:
        return ""
    return re.sub(r"[\W_]+", " ", path)


def clean_snippet(text: str | None, limit: int = 300) -> str:
    if not text:
        return ""
    collapsed = " ".join(re.sub(r"<[^>]{0,500}>", " ", text).split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 1].rstrip() + "…"
