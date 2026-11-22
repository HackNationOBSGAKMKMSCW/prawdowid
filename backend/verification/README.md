# verification: pełny przepływ weryfikacji

Input użytkownika przechodzi przez cały potok, a na końcu są **dwie niezależne oceny**. Każda oddaje wynik zaraz po zakończeniu, nie czekając na drugą.

```
tekst, submitted_at
  ├─ textAnalysis.run                    ekstrakcja twierdzeń            ┐
  │    └─ knownDisinfo.run               baza EUvsDisinfo (równolegle z wyszukaniem, patrz niżej)
  ├─ apiReading.run + trustedSources.run wyszukanie (równolegle)         │ zdarzenie "evidence"
  └─ articleScraping.run                 pobranie artykułów (≥ 2 strony) ┘
        ├─ inputDataAnalysis.analyze_async  ocena INPUTU: manipulacje A–G, spójność dat  → "input_analysis"
        └─ prawdowid_analysis.run           ocena TEZ: prawda / fałsz / brak danych      → "claims_verdict"
             + nadpisanie twierdzeń znalezionych w bazie EUvsDisinfo
```

Obie oceny dostają te same pobrane artykuły pod tymi samymi identyfikatorami (`art1`, `art2`…). Cytat z dowolnej oceny można więc powiązać z `evidence.data.scraping.articles`.

## Użycie z kodu

```python
import verification

# 1) strumień: evidence, potem oceny w kolejności ukończenia (np. pod SSE / WebSocket)
async for event in verification.stream(text, submitted_at=sent_at):
    send_to_front(event.model_dump(mode="json"))

# 2) zadanie z osobnymi częściami (np. pod dwa endpointy)
job = verification.start(text, submitted_at=sent_at)
job.request_id
await job.input_analysis  # VerificationEvent
await job.claims_verdict  # VerificationEvent

# 3) wszystko naraz
report = await verification.run(text)  # VerificationReport
```

`submitted_at` to czas wysłania zapytania przez użytkownika. Domyślnie przyjmowana jest chwila wywołania. `timeout` (domyślnie 240 s) ogranicza **każdą ocenę osobno**.

## Zdarzenie (`VerificationEvent`)

```jsonc
{
  "request_id": "3f2a…",                 // ten sam dla wszystkich części jednego zapytania
  "part": "evidence",                    // evidence | input_analysis | claims_verdict
  "status": "ok",                        // ok | error
  "data": {…},                           // null przy błędzie
  "error": null,                         // {"kind": "Timeout" | "LLMError" | "evidence_failed" | …, "message": "…"}
  "duration_ms": 5466,
  "finished_at": "2026-11-22T08:30:05Z"
}
```

| `part` | `data` |
|---|---|
| `evidence` | `{"statements": [...], "scraping": ScrapingReport}`: tytuły, daty, pełne treści, autorzy, `submitted_at`, niezmieniony `user_input`, wszystkie linki ([articleScraping/README.md](../articleScraping/README.md)) |
| `input_analysis` | `inputDataAnalysis.AnalysisResult`: `manipulation` (fragmenty, kategorie, wynik 0–100) i `dates` (`dates_consistent`, `issues`) |
| `claims_verdict` | `prawdowid_analysis.TextVerdict`: `verdict` dla tekstu, `claims[]` z dowodami (`evidence[].url`, dosłowny `quote`) |

Zasady:
- Błąd jednej oceny nie wpływa na drugą.
- Gdy nie uda się zebrać materiałów (np. textAnalysis zawiedzie), obie oceny kończą się błędem `evidence_failed`.
- Brak artykułów nie przerywa przepływu. Ocena inputu i tak sprawdza manipulacje, a werdykt zwykle zwraca „brak danych”.

## Baza EUvsDisinfo: zweryfikowana rosyjska dezinformacja

Zaraz po ekstrakcji twierdzeń [knownDisinfo](../knownDisinfo/README.md) sprawdza, czy któreś z nich jest w bazie EUvsDisinfo. Szuka przez MCP, a LLM-sędzia potwierdza, że wpis to ta sama teza. Wynik wpływa wyłącznie na `claims_verdict` i nie ma osobnego zdarzenia.

- **Trafione twierdzenie** dostaje:
  - `verdict: "falsz"`, `verdict_label: "Zweryfikowana rosyjska dezinformacja"`, `confidence: "wysoka"`;
  - pole `known_disinformation` z tytułem, `url`, opisem przypadku i uzasadnieniem dopasowania;
  - przypadek jako pierwszy dowód w `evidence`;
  - wpis w `adjustments`.

  Werdykt dla całego tekstu jest liczony od nowa tą samą regułą co w `prawdowid_analysis` (`aggregate`).
- **`data.known_disinfo`** jest zawsze obecne i ma postać `{status: ok | disabled | error, source: "EUvsDisinfo", matches: [...], warnings: [...]}`.
- **Gdy baza nie działa** albo brak klucza, werdykt wychodzi bez zmian, a powód jest w `known_disinfo`.
- **Gdy padnie ocena tez na źródłach**, a w bazie jest trafienie, zdarzenie i tak ma status `ok`. Trafienia są rozstrzygające same w sobie, a pozostałe twierdzenia dostają `blad_analizy`.
- **Limit czasu** (`timeout`) obejmuje osobno werdykt i osobno sprawdzenie w bazie.

## Podpięcie przyszłego REST API (szkic, nie jest wdrożony)

```python
# Wariant A: jeden strumień SSE
@app.post("/api/verify/stream")
async def verify_stream(body: VerifyIn):
    async def events():
        async for event in verification.stream(body.text, submitted_at=body.submitted_at):
            yield f"event: {event.part}\ndata: {event.model_dump_json()}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


# Wariant B: start i dwa endpointy, które front wywołuje razem
JOBS: dict[str, verification.VerificationJob] = {}


@app.post("/api/verify")
async def verify(body: VerifyIn):
    job = verification.start(body.text, submitted_at=body.submitted_at)
    JOBS[job.request_id] = job
    return {"request_id": job.request_id}


@app.get("/api/verify/{request_id}/input")
async def input_part(request_id: str):
    return await JOBS[request_id].input_analysis


@app.get("/api/verify/{request_id}/claims")
async def claims_part(request_id: str):
    return await JOBS[request_id].claims_verdict
```

## CLI

```powershell
cd backend
.venv\Scripts\python -m verification "Szczepienia na COVID są obowiązkowe od przyszłego tygodnia."
.venv\Scripts\python -m verification --jsonl "Ziemia jest płaska."   # jedna linia JSON na zdarzenie
```

Wyniki trafiają na stdout, a logi postępu modułów na stderr. `--jsonl` pomija `user_input`. Kod wyjścia 1 oznacza, że któraś część skończyła się błędem.

## Konfiguracja

Pakiety oceny są w `analysis/`, który zostaje dołączony do `sys.path` (inną lokalizację ustawia `PRAWDOWID_ANALYSIS_DIR`). Wszystkie zależności są w `backend/.venv`.

| Ocena | Plik konfiguracji | Zmienne |
|---|---|---|
| inputu (`inputDataAnalysis`) | `analysis/inputDataAnalysis/.env` | `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` |
| tez (`prawdowid_analysis`) | `analysis/.env`, potem `backend/.env` | `FREELLM_*` (lub starsze `OPENAI_*`, `LLM_MODEL`) |

Oba pliki definiują `LLM_MODEL`. Konfiguracja oceny inputu ładuje się pierwsza, więc każda ocena używa swojego modelu. Werdykt korzysta wyłącznie z pobranych artykułów i fact-checków (`use_corpus=False`), bo `analysis/data/sources` zawiera tylko przykłady testowe.
