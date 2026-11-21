"""Wektor rzadki do BM25 w Qdrant: tokenizacja PL -> częstości termów (TF).

IDF liczy Qdrant (`modifier: idf` w konfiguracji kolekcji), więc tutaj tylko TF
z prostą normalizacją długości dokumentu w duchu BM25 (k1, b).
"""

import re
import zlib
from collections import Counter

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Krótka lista polskich słów funkcyjnych.
STOPWORDS = frozenset(
    """
    a aby albo ale ani aż bez bo by być był była było były będzie będą co czy dla do gdy
    gdzie go i ich ile im iż ja jak jako je jego jej jest jeszcze jeśli już ją każdy kiedy
    kto która które którego której który których ku lub ma mają może mu na nad nie niż no
    o od oraz po pod przed przez przy roku się są ta tak także te tego tej ten też to tu
    tylko tym u w we wraz z za ze że żeby
    """.split()  # noqa: SIM905
)

STEM_LEN = 6  # prymitywny stemming: prefiks, wystarcza dla odmiany polskich wyrazów
_K1 = 1.2
_B = 0.75
_AVG_DOC_TOKENS = 120.0


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if raw in STOPWORDS or (len(raw) < 2 and not raw.isdigit()):
            continue
        tokens.append(raw if raw.isdigit() else raw[:STEM_LEN])
    return tokens


def token_id(token: str) -> int:
    # Stabilny między procesami (w odróżnieniu od hash()), mieści się w uint32.
    return zlib.crc32(token.encode("utf-8"))


def sparse_vector(text: str, *, is_query: bool = False) -> dict[str, list]:
    """Zwraca `{"indices": [...], "values": [...]}` w formacie Qdrant.

    Dla zapytania wagi to 1.0 na term (IDF dokłada Qdrant). Dla dokumentu
    nasycone TF z normalizacją długości (BM25).
    """
    counts = Counter(token_id(t) for t in tokenize(text))
    if not counts:
        return {"indices": [], "values": []}
    indices = sorted(counts)
    if is_query:
        values = [1.0] * len(indices)
    else:
        doc_len = sum(counts.values())
        norm = _K1 * (1 - _B + _B * doc_len / _AVG_DOC_TOKENS)
        values = [round(counts[i] * (_K1 + 1) / (counts[i] + norm), 4) for i in indices]
    return {"indices": indices, "values": values}
