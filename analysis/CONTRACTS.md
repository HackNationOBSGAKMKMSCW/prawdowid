# Kontrakty danych

> **Status: szkic do zatwierdzenia na SYNC 1.** Po zatwierdzeniu każda zmiana idzie przez PR
> i wpis w sekcji „Historia zmian”.

Kontrakty opisują dane przekazywane między częścią A (dane i retrieval) a częścią B
(weryfikacja i produkt). Daty w formacie ISO 8601, czas w UTC.

## Granica A ↔ B

```python
def retrieve(query: str, k: int = 6, filters: dict | None = None) -> list[Passage]: ...
```

`filters` pozwala zawęzić wyniki, np. `{"source_type": ["official_primary"]}`.
Implementacje: `prawdowid_analysis.rag.get_retriever()` — `RETRIEVER=mock` (atrapa,
bez sieci) albo `RETRIEVER=qdrant` (hybryda dense + BM25, fuzja RRF).

## Wejście analizy (`AnalysisInput`)

Zespół analizy dostaje gotowe twierdzenia i źródła (URL + oczyszczony tekst). Ekstrakcja
twierdzeń i pobieranie URL dzieją się poza `analysis/`.

```json
{
  "request_id": "req_001",
  "claims": [{ "claim_id": "clm_001", "text": "...", "type": "legal", "check_worthy": true }],
  "sources": [
    {
      "url": "https://...",
      "title": "...",
      "publisher": "...",
      "published_at": "2026-10-03",
      "fetched_at": "2026-11-21T10:15:32Z",
      "source_type": "official_primary",
      "text": "<clean_text>"
    }
  ]
}
```

- `text` to `clean_text`: offsety `char_start`/`char_end` pasaży liczone są względem niego.
- `claims[].run_id` jest opcjonalne na wejściu.
- Ingest: `ingest_sources(sources) -> {"added", "skipped", "replaced"}`.
  `doc_id = "doc_" + sha256(znormalizowany URL)[:12]`; ten sam URL i ten sam `text_hash` →
  `skipped`, ten sam URL i inny tekst → `replaced` (reindeks), duplikat URL w partii → `skipped`.
- `chunk_id = f"{doc_id}_c{i}"` (numeracja od 0).

## Wyjście analizy (`AnalysisOutput`), konsumuje backend

```json
{
  "request_id": "req_001",
  "results": [
    { "claim": { "...": "claim" }, "passages": [], "evidence": [], "verdict": { "...": "verdict" } }
  ],
  "ingest": { "added": 8, "skipped": 1, "replaced": 0 }
}
```

Modele: `analysis/src/prawdowid_analysis/schemas.py` (`SourceIn`, `AnalysisInput`,
`IngestReport`, `ClaimResult`, `AnalysisOutput`).

## `passage` (wyjście `retrieve`)

```json
{
  "chunk_id": "doc_001_c3",
  "doc_id": "doc_001",
  "title": "...",
  "publisher": "...",
  "url": "...",
  "published_at": "2026-10-03",
  "fetched_at": "2026-11-21T10:15:32Z",
  "source_type": "official_primary",
  "text": "...",
  "char_start": 1200,
  "char_end": 1340,
  "text_hash": "sha256:...",
  "rerank_score": 0.91
}
```

- `source_type`: `official_primary`, `public_data`, `fact_check`, `news_agency`, `research`, `media`.
- `char_start` i `char_end` dotyczą dokładnie zapisanego `clean_text` dokumentu. `text_hash` pozwala wykryć, że dokument zmieniono i offsety są nieaktualne.

## `claim`

```json
{
  "claim_id": "clm_001",
  "run_id": "run_001",
  "text": "...",
  "type": "event",
  "check_worthy": true
}
```

- `type`: `legal`, `numeric`, `scientific`, `quote`, `event`, `opinion`.

## `evidence`

```json
{
  "evidence_id": "ev_001",
  "claim_id": "clm_001",
  "chunk_id": "doc_001_c3",
  "quote": "...",
  "quote_verified": true,
  "stance": "supports"
}
```

- `stance`: `supports`, `refutes`, `neutral`, `insufficient`.
- `quote_verified`: czy cytat znaleziono w tekście pasażu. Dowód z `false` nie może wspierać werdyktu.

## `verdict`

```json
{
  "claim_id": "clm_001",
  "outcome_class": "verdict",
  "outcome": "insufficient_evidence",
  "strength": {
    "level": "low",
    "factors": ["0 niezależnych źródeł T1-T2", "brak cytatu wspierającego"]
  },
  "explanation_pl": "...",
  "unresolved": ["..."],
  "limitations": ["..."],
  "evidence_ids": ["ev_001"],
  "flags": ["conflicting_sources"],
  "handover": { "recommended": true, "created": false, "case_id": null }
}
```

- `outcome_class`: `verdict` albo `status`.
- `outcome` dla `verdict`: `confirmed`, `false`, `misleading`, `insufficient_evidence`, `not_verifiable`.
- `outcome` dla `status`: `error`, `cannot_check`, `needs_clarification`, `out_of_scope`. Status nigdy nie jest werdyktem.
- `strength.level`: `high`, `medium`, `low`. Poziom wynika z `factors`, a nie z oceny modelu.
- `flags`: `conflicting_sources`, `missing_context`, `stale_source`, `source_status_warning`.
- `handover`: `recommended` (zalecono przekazanie) jest oddzielne od `created` (sprawę faktycznie utworzono).

## `run` (zapis przebiegu sprawdzenia)

```json
{
  "run_id": "run_001",
  "channel": "web",
  "received_at": "2026-11-21T10:15:00Z",
  "input_type": "text",
  "input_masked": "...",
  "claim_ids": ["clm_001"],
  "duration_ms": 12400,
  "models": [{ "name": "...", "tokens_in": 0, "tokens_out": 0 }],
  "cost_estimate_usd": 0.0,
  "errors": [],
  "security_events": 0
}
```

- `channel`: `web`, `discord`, `sms` lub inny adapter.
- `input_masked`: treść zgłoszenia po maskowaniu danych osobowych. Oryginał nie jest zapisywany.

## Historia zmian

| Data | Zmiana | Kto |
| --- | --- | --- |
| 2026-11-21 | Pierwszy szkic | zespół |
| 2026-11-21 | Wejście/wyjście analizy (`AnalysisInput`, `AnalysisOutput`), reguły `doc_id`/dedupe, `claim.run_id` opcjonalne | osoba A |
