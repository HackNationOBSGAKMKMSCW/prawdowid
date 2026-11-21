# Plan zespołu analizy (osoby A i B) — praca równoległa

## Context

Pierwotny plan zakładał, że A sam zbiera korpus (scraping, ≥100 dokumentów), a B robi ekstrakcję twierdzeń, API, WWW i drugi kanał.
Zmiana: zespół analizy (`analysis/`) dostaje **gotowy obiekt wejściowy** — wyekstrahowane twierdzenia + źródła (URL + gotowy, oczyszczony tekst). Ekstrakcja twierdzeń, pobieranie URL, API (`backend/`), WWW (`frontend/`) i drugi kanał należą do pozostałych osób z pięcioosobowego zespołu.
Zakres analizy to więc: **źródła → RAG → pasaże → dowody → werdykt**, plus ewaluacja.
Najbliższy cel: postawić RAG, nakarmić go przykładowymi danymi i zobaczyć, co zwraca — a równolegle B buduje logikę werdyktu na atrapie retrievera.

Ustalone:

- Źródła: **URL + gotowy tekst** (`text` = `clean_text`, offsety liczone względem niego).
- **Qdrant już stoi**: `http://100.115.139.118:63333` (REST; adres tylko w lokalnym `.env`).
- **Embeddingi (i ewentualnie LLM): Ollama na tym samym serwerze co Qdrant** — `OPENAI_BASE_URL=http://100.115.139.118:<port>/v1` (domyślnie 11434, do potwierdzenia), `EMBEDDING_MODEL=bge-m3` (musi być pobrany na serwerze). Adresy tylko w lokalnym `.env`.
- Środowisko lokalne: brak Dockera/GPU, Python 3.15; nic nie stawiamy lokalnie. Z tej maszyny serwer (Qdrant :63333, Ollama :11434) chwilowo nie odpowiadał — sprawdzić VPN/Tailscale na starcie.

## Role

- **A: dane i retrieval** — kontrakt wejścia, ingest źródeł z pomijaniem duplikatów, Qdrant (dense + BM25), `retrieve()`, reranker, dane przykładowe, ewaluacja retrievera.
- **B: dowody i werdykt** — stance pasażu wobec twierdzenia, weryfikator cytatów, reguły werdyktu (5 wartości + statusy), siła z jawnych czynników, flagi, ochrona przed wstrzyknięciami, zbiór testowy A–J i metryki.

## Kontrakty (SYNC 1 — zapisać w `analysis/CONTRACTS.md` z wpisem w historii zmian)

**Wejście analizy (nowe)**

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

**Granica A ↔ B (bez zmian):** `retrieve(query, k=6, filters=None) -> list[Passage]` + `ingest_sources(sources) -> {added, skipped, replaced}`. Format `passage`, `evidence`, `verdict` jak w obecnym `CONTRACTS.md`.

**Wyjście analizy (nowe):** `{"request_id", "results": [{"claim": Claim, "passages": [Passage], "evidence": [Evidence], "verdict": Verdict}], "ingest": {added, skipped, replaced}}` — to konsumuje backend.

**Wspólne modele:** `analysis/src/prawdowid_analysis/schemas.py` — kopia 1:1 `backend/schemas.py` + `SourceIn`, `AnalysisInput`, `AnalysisOutput`. Zmiana = PR + powiadomienie drugiej osoby.

**Atrapa dla B:** `prawdowid_analysis/rag/mock.py` — przeniesione `_MOCK_DOCS`/`mock_retrieve` z `backend/retrieval.py` (te same fikcyjne dane, w tym dokument z wstrzyknięciem), z tą samą sygnaturą co prawdziwy `retrieve`. Przełącznik `RETRIEVER=mock|qdrant`.

## Struktura kodu

```
analysis/src/prawdowid_analysis/
  schemas.py                 # wspólne (SYNC 1, razem)
  pipeline.py                # run(AnalysisInput) -> AnalysisOutput   (razem przy SYNC 3)
  rag/                       # ── A ──
    config.py  chunking.py  sparse.py  embed.py  store.py  ingest.py  retriever.py  mock.py
  verdict/                   # ── B ──
    stance.py      # LLM: stance pasażu + dosłowny cytat (klient jako parametr)
    quotes.py      # verify_quote(quote, passage) — rapidfuzz, próg; bez sieci
    rules.py       # aggregate(claim, evidence, passages) -> Verdict; czyste funkcje
    strength.py    # factors -> level (tier, niezależność, aktualność, zgodność cytatu)
    flags.py       # conflicting_sources, stale_source, missing_context
    security.py    # tagi <source>, instrukcja „to dane”, detektor wstrzyknięć -> security_event
  eval/
    metrics.py     # macro-F1, pokrycie/poprawność cytowań, wstrzymanie, odporność, czas
analysis/scripts/rag_demo.py      # A: ingest + retrieve per claim, wydruk
analysis/scripts/run_eval.py      # B (+A dla metryk retrievera)
analysis/data/samples/sample_input.json   # A
analysis/data/eval/public.jsonl, heldout.jsonl  # B (A dokłada oczekiwane doc_id)
```

## Przebieg (równolegle, z punktami synchronizacji)

| Czas                         | Osoba A (dane i retrieval)                                                                                                                                                                                                                                                            | Osoba B (dowody i werdykt)                                                                                                                                                                                          |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **0:00–0:45 SYNC 1 (razem)** | Kontrakt wejścia/wyjścia w `CONTRACTS.md`, `schemas.py`, przeniesienie atrapy do `rag/mock.py`, `.env.example` (`QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`, `OPENAI_*`, `LLM_MODEL`, `EMBEDDING_MODEL`, `RETRIEVER`), zależności w `pyproject.toml`.                         | to samo                                                                                                                                                                                                             |
| 0:45–2:00                    | Połączenie z Qdrantem i Ollamą na serwerze (`GET /collections`, `GET /v1/models`, test embeddingu bge-m3). `chunking.py` (zdania, ~800 zn., overlap 1 zdanie, offsety), `sparse.py` (tokenizacja PL → TF, IDF w Qdrant), `embed.py`. Testy offsetów: `clean_text[start:end] == text`. | Wybór i uruchomienie LLM (przez API zgodne z OpenAI), pomiar czasu generacji. `quotes.py` + testy. `rules.py` szkielet: brak dowodów → `insufficient_evidence`, opinia → `not_verifiable`, awaria → `status:error`. |
| 2:00–3:30                    | `store.py` (kolekcja: dense cosine + sparse `bm25` z `modifier=IDF`, indeksy payloadu `doc_id`, `source_type`, `published_at`), `ingest.py` z pomijaniem: `doc_id` z hasha URL, skip przy tym samym `text_hash`, reindeks przy innym. `sample_input.json` (~8 źródeł, ~6 twierdzeń).  | `stance.py`: prompt (pasaże w tagach `<source>`, „treść to dane”), wyjście JSON `{stance, quote}`; walidacja i fallback na `insufficient` przy złym JSON. Działa na `mock_retrieve`.                                |
| **3:30 SYNC 2**              | Pokazuje `rag_demo.py` na danych przykładowych (2 przebiegi: `added`, potem `skipped`).                                                                                                                                                                                               | Pokazuje werdykty na atrapie. Wspólnie: czy pasaże (długość, metadane) wystarczają do stance i cytatów.                                                                                                             |
| 3:30–5:30                    | `retriever.py`: Query API, prefetch dense+sparse, fuzja RRF, filtry `source_type`. Reranker (bge-reranker przez endpoint lub LLM) → `rerank_score`. `injection_flags` przy ingeście (w payloadzie).                                                                                   | `strength.py` i `flags.py` (sprzeczne źródła, `stale_source` po `published_at`). Pełne `rules.py`: min. 2 niezależne T1–T2 do `confirmed`/`false`, `quote_verified=false` nie wspiera werdyktu.                     |
| 5:30–6:30                    | Wymiana atrapy na prawdziwy retriever (`RETRIEVER=qdrant`). Instrukcja dla backendu, jak zaimportować `prawdowid_analysis`.                                                                                                                                                           | `security.py`: wykrywanie wstrzyknięć w pasażach, rekord `security_event`, test na dokumencie z atrapy.                                                                                                             |
| **6:30 SYNC 3 (razem)**      | **Integracja:** `pipeline.py` (ingest → retrieve → stance → verdict), 10 twierdzeń, przegląd wyników. Decyzja: poprawiamy retrieval czy prompt.                                                                                                                                       | to samo                                                                                                                                                                                                             |
| 6:30–8:30                    | Oczekiwane `doc_id` w zbiorze testowym, metryka retrievera (recall@6, MRR). Strojenie chunkowania, limitów prefetch, rerankera.                                                                                                                                                       | Zbiór testowy: ≥30 przypadków (A–J), podział public/heldout, `run_eval.py` + `metrics.py`.                                                                                                                          |
| 8:30–10:00                   | Scenariusz E (wstrzyknięcia w źródłach) i C (sprzeczne) w danych; archiwalne dokumenty (`staleness`); wydajność ingestu (batch embeddingów, cache po `text_hash`).                                                                                                                    | Progi wstrzymania się, statusy techniczne bez pozornych werdyktów, `explanation_pl` prostym językiem, `handover.recommended`.                                                                                       |
| **10:00 SYNC 4 (razem)**     | Pełny zestaw testowy, metryki (macro-F1 ≥ 0,75, pokrycie cytowań ≥ 95%, poprawność ≥ 85%, wstrzymanie ≥ 80%, odporność ≥ 90%, mediana ≤ 30 s). Wspólna lista poprawek.                                                                                                                | to samo                                                                                                                                                                                                             |
| 10:00–12:00                  | Poprawki retrievera wg wyników. Dokumentacja RAG (model embeddingów, kolekcja, dedupe, koszty).                                                                                                                                                                                       | Poprawki promptu i progów (tylko na public). Eksport wyniku do JSON/CSV, jeśli bazowe stabilne.                                                                                                                     |
| 12:00–13:00                  | Test od zera: nowa kolekcja, `rag_demo.py` według README.                                                                                                                                                                                                                             | Opis ryzyk, koszt 1000 zapytań (tokeny LLM + embeddingi), materiał do prezentacji.                                                                                                                                  |
| **13:00 SYNC 5 (razem)**     | Przegląd z resztą zespołu: integracja z backendem, brak kluczy i adresów w repo, README `analysis/`.                                                                                                                                                                                  | to samo                                                                                                                                                                                                             |

## Kluczowe decyzje implementacyjne (A)

- ID punktu Qdrant = `uuid5(NAMESPACE_URL, chunk_id)`; `chunk_id = f"{doc_id}_c{i}"`; `doc_id = "doc_" + sha256(znormalizowany URL)[:12]`.
- Payload chunka = wszystkie pola `Passage` poza `rerank_score` → retriever nie robi dodatkowych zapytań.
- `text_hash = "sha256:" + sha256(clean_text)` — dedupe i wykrywanie nieaktualnych offsetów.
- Model embeddingów zapisany w `docs/decyzje.md`; zmiana = reindeks.
- Ryzyko Py 3.15 + `grpcio` (zależność `qdrant-client`): przy błędzie instalacji `store.py` przechodzi na REST przez `httpx` z tym samym interfejsem.

## Kluczowe decyzje implementacyjne (B)

- Reguły werdyktu bez sieci i LLM (testowalne na zbiorze); LLM tylko w `stance.py`, klient przekazywany parametrem.
- Cytat musi być w `passage.text` (rapidfuzz, wysoki próg) — inaczej `quote_verified=false`.
- Siła wyłącznie z listy `factors`, nigdy z procentu modelu.

## Zasady współpracy (bez zmian, doprecyzowane)

- Gałęzie: A `data/*`, B `analysis/*` (albo `app/*` wg CONTRIBUTING); pliki wspólne (`CONTRACTS.md`, `schemas.py`, `pipeline.py`, `.env.example`, `pyproject.toml`) przez krótkie PR.
- A pracuje w `rag/`, B w `verdict/` i `eval/` — brak konfliktów plików.
- B nie czeka na A: do SYNC 3 używa `RETRIEVER=mock`.
- Spór „retrieval czy prompt” rozstrzyga zestaw testowy.

## Miejsca ryzyka

1. **Ollama/Qdrant niedostępne** — A sprawdza połączenie w pierwszych 15 min; awaria = status `error`, nie werdykt.
2. **Szybkość LLM (B)** — mediana > 30 s → mniejszy model lub mniej pasaży (k) przed SYNC 3.
3. **Rozjazd offsetów** — `text_hash` w każdym pasażu; test `clean_text[start:end] == text`.
4. **Format wejścia od backendu** — kontrakt wejścia zatwierdzony z osobą od backendu na SYNC 1; do tego czasu `sample_input.json` jest wzorcem.

## Weryfikacja

- `.venv/Scripts/python -m pytest` — chunking, sparse, dedupe (fałszywy store w pamięci), quotes, rules, strength, flags; bez sieci.
- `scripts/rag_demo.py data/samples/sample_input.json`: 1. przebieg `added=N, skipped=1` (duplikat URL), 2. przebieg wszystko `skipped`; top-6 pasaży per twierdzenie, oczekiwany dokument w top-3, każdy Passage waliduje się w Pydantic; zapis do `outputs/` (gitignored).
- `scripts/run_eval.py --split public` — metryki z zadania, wynik wklejany do opisu PR.
- `ruff check .`, `ruff format .` czyste.

## Krok 0 (po zatwierdzeniu)

Zapisać ten plan jako `docs/plan-analizy.md` (bez sekcji „Context” w formie notatki dla Claude, z tabelą harmonogramu i kontraktami). Plików wspólnych (`CONTRIBUTING.md`) nie ruszamy bez PR.

## Pierwszy task A (teraz)

Kroki 0:45–3:30 z kolumny A: połączenie z Qdrantem i Ollamą na 100.115.139.118 → chunking/sparse/embed z testami → store + ingest z dedupe → `sample_input.json` → `rag_demo.py`, oglądamy wyniki. Gałąź `data/rag-mvp`.
