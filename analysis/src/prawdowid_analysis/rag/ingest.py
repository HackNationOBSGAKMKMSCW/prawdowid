"""Ingest źródeł do indeksu z pomijaniem duplikatów.

- `doc_id = "doc_" + sha256(znormalizowany URL)[:12]`
- ten sam `doc_id` i ten sam `index_key` -> `skipped`
- ten sam `doc_id`, inny `index_key` -> stare chunki usuwane, `replaced`

`index_key = text_hash | INGEST_VERSION | max_chars`: zmiana tekstu, logiki ingestu
(chunking, detektor wstrzyknięć; wtedy podbić `INGEST_VERSION`) albo rozmiaru chunków
powoduje reindeks dokumentu.
- duplikat URL w jednej partii -> `skipped`
"""

import hashlib
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..schemas import IngestReport, SourceIn
from .chunking import chunk_text
from .embed import Embedder
from .injection import detect_injection
from .sparse import sparse_vector
from .store import DENSE, SPARSE, VectorStore

INGEST_VERSION = 2
_TRACKING_PARAMS = ("utm_", "fbclid", "gclid")


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith(_TRACKING_PARAMS)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(sorted(query)), "")
    )


def make_doc_id(url: str) -> str:
    return "doc_" + hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()[:12]


def make_text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def build_payloads(source: SourceIn, max_chars: int = 800) -> list[dict]:
    doc_id = make_doc_id(source.url)
    text_hash = make_text_hash(source.text)
    index_key = f"{text_hash}|v{INGEST_VERSION}|{max_chars}"
    payloads = []
    for ch in chunk_text(source.text, max_chars=max_chars):
        payloads.append(
            {
                "chunk_id": f"{doc_id}_c{ch.index}",
                "chunk_index": ch.index,
                "doc_id": doc_id,
                "title": source.title,
                "publisher": source.publisher,
                "url": source.url,
                "published_at": source.published_at,
                "fetched_at": source.fetched_at,
                "source_type": source.source_type,
                "text": ch.text,
                "char_start": ch.start,
                "char_end": ch.end,
                "text_hash": text_hash,
                "index_key": index_key,
                "injection_flags": detect_injection(ch.text),
            }
        )
    return payloads


def ingest_sources(
    sources: list[SourceIn],
    store: VectorStore | None = None,
    embedder: Embedder | None = None,
    max_chars: int | None = None,
) -> IngestReport:
    """Bez `store`/`embedder` używa Qdranta i embeddera z `analysis/.env`."""
    if store is None or embedder is None:
        from .config import load_config
        from .embed import embedder_from_config
        from .store import store_from_config

        cfg = load_config()
        store = store or store_from_config(cfg)
        embedder = embedder or embedder_from_config(cfg)
        max_chars = max_chars or cfg.chunk_chars
    max_chars = max_chars or 800
    report = IngestReport()
    seen: set[str] = set()
    to_index: list[tuple[str, bool, list[dict]]] = []  # (doc_id, czy zastąpić, payloady)

    # 1. Decyzja per dokument (bez embeddingów)
    for source in sources:
        doc_id = make_doc_id(source.url)
        if doc_id in seen:
            report.skipped += 1
            continue
        seen.add(doc_id)

        payloads = build_payloads(source, max_chars=max_chars)
        if not payloads:
            report.skipped += 1
            continue
        existing = store.get_index_key(doc_id)
        if existing == payloads[0]["index_key"]:
            report.skipped += 1
            continue
        to_index.append((doc_id, existing is not None, payloads))

    if not to_index:
        return report

    # 2. Jeden batch embeddingów dla całej partii (embedder sam dzieli na porcje)
    all_payloads = [p for _, _, payloads in to_index for p in payloads]
    dense = embedder.embed([p["text"] for p in all_payloads])
    store.ensure_collection(len(dense[0]))

    # 3. Zastąpienie starych wersji i zapis
    for doc_id, replace, _ in to_index:
        if replace:
            store.delete_doc(doc_id)
            report.replaced += 1
        else:
            report.added += 1
    store.upsert(
        [
            {
                "id": point_id(p["chunk_id"]),
                "vector": {DENSE: vec, SPARSE: sparse_vector(p["text"])},
                "payload": p,
            }
            for p, vec in zip(all_payloads, dense, strict=True)
        ]
    )
    return report
