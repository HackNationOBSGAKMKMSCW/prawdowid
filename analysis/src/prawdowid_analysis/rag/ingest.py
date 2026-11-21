"""Ingest źródeł do indeksu z pomijaniem duplikatów.

- `doc_id = "doc_" + sha256(znormalizowany URL)[:12]`
- ten sam `doc_id` i ten sam `text_hash` -> `skipped`
- ten sam `doc_id`, inny `text_hash` -> stare chunki usuwane, `replaced`
- duplikat URL w jednej partii -> `skipped`
"""

import hashlib
import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..schemas import IngestReport, SourceIn
from .chunking import chunk_text
from .embed import Embedder
from .sparse import sparse_vector
from .store import DENSE, SPARSE, VectorStore

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
                "injection_flags": [],
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
    collection_ready = False

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
        existing = store.get_doc_hash(doc_id)
        if existing == payloads[0]["text_hash"]:
            report.skipped += 1
            continue

        dense = embedder.embed([p["text"] for p in payloads])
        if not collection_ready:
            store.ensure_collection(len(dense[0]))
            collection_ready = True
        if existing is not None:
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
                for p, vec in zip(payloads, dense, strict=True)
            ]
        )
    return report
