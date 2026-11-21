# observability: logowanie aplikacji

Logi trafiają do `backend/logs/app.jsonl` w formacie JSON Lines, czyli jeden obiekt na linię. Ostrzeżenia lecą też krótko na stderr. Pakiet nie ma dodatkowych zależności, wystarczy biblioteka standardowa.

## Podpięcie

Wystarczy jedna linia w punkcie startowym procesu (serwer API, CLI, bot):

```python
from observability import init

init()
```

W FastAPI dochodzi middleware: jedno żądanie HTTP daje jedno `request_id`, a odpowiedź dostaje nagłówek `X-Request-ID`.

```python
from observability import ObservabilityMiddleware

app.add_middleware(ObservabilityMiddleware)
```

Bez middleware'u, czyli w CLI albo w bocie, granicę żądania wyznacza pierwszy śledzony etap. Można ją też ustawić ręcznie przez `with request_scope("nazwa"): ...`.

## Co jest logowane automatycznie (bez zmian w Waszym kodzie)

`init()` podmienia w runtime wybrane funkcje na wrappery. Kod modułów zostaje nietknięty.

| Zdarzenie | Źródło | Pola |
|---|---|---|
| `llm_call` | każde `chat.completions.create/parse` i `responses.create` z SDK `openai` (dowolny moduł) | model, latency_ms, prompt/completion tokens, cost_usd, ok, error, status_code |
| `search_call` / `search_error` / `search_retry` | `apiReading.base.BaseApiClient._request` (Google Fact Check, Diffbot i każdy nowy klient) | provider, host, status_code, latency_ms, error, retry_after |
| `prompt_injection` | `textAnalysis.InputSanitizer.sanitize`, wyciek canary / niedozwolona kategoria w odpowiedzi LLM, tekst i źródła `inputDataAnalysis` | kind, pattern, source, detector, snippet (≤80 zn.), text_sha256, text_length |
| `abstain` | wyciek instrukcji (blokada), `whatsappAdapter.overall_verdict` = `no_data`/`unverified` | reason |
| `evidence_empty` | `apiReading.run` / `run_full_text` bez wyników | reason: `no_results` / `search_failed` |
| `stage` | `textAnalysis.run/run_url/analyze/...`, `apiReading.run`, `articleScraping.run`, `inputDataAnalysis.analyze_async`, `whatsappAdapter.*Pipeline.check` | stage_name, duration_ms, ok, error |
| `request_summary` | koniec żądania | czas, liczba wywołań LLM i wyszukiwań, tokeny, koszt, injection, abstain, czasy etapów |

Jeśli któryś moduł się nie importuje albo funkcja zmieniła nazwę, patch jest pomijany i aplikacja działa dalej. Co zostało podpięte, pokazuje `observability.status()` oraz zdarzenie `instrumentation` w logu.

## Konwencje dla zespołu

Jak dodać logowanie do nowego modułu, krok po kroku z przykładami: [NOWE_MODULY.md](NOWE_MODULY.md).

- Zamiast `print` używaj `logger = logging.getLogger(__name__)`. Logi z modułów też trafiają do pliku, oznaczone `request_id`.
- Zdarzenia domenowe zapisuj przez `log_event("nazwa", **pola)`, a wstrzymanie werdyktu przez `log_abstain("powód")`.
- Nowy etap do zmierzenia oznacz dekoratorem `@traced("modul.etap")`. Bez zmiany kodu możesz go też dodać zmienną `LOG_TRACE_TARGETS`.
- Nie loguj pełnego tekstu użytkownika ani kluczy. Formatter maskuje pola `*key*`, `token`, `authorization` oraz `key=...` w URL-ach, ale to tylko siatka bezpieczeństwa.
- Instrumentacja łapie funkcje przez nazwę modułu. Kopie zrobione przez `from x import f` są podmieniane, jeśli moduł załadowano przed `init()`. Aliasy (`import f as g`) i referencje zapisane w obiektach przed `init()` nie są podmieniane, dlatego `init()` warto wywołać jak najwcześniej.

## Konfiguracja (env)

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `LOG_ENABLED` | `true` | `false` sprawia, że `init()` nic nie robi |
| `LOG_LEVEL` | `INFO` | poziom pliku |
| `LOG_FILE` | `backend/logs/app.jsonl` | rotacja 5 × 5 MB |
| `LOG_CONSOLE` | `false` | `true` wypisuje wszystkie zdarzenia na stderr; domyślnie trafiają tam tylko WARNING i wyższe |
| `LOG_PRICING_FILE` | brak | dodatkowy JSON z cenami modeli (format jak `pricing.json`) |
| `LOG_TRACE_TARGETS` | brak | np. `pkg.mod:run=pkg.run,pkg.mod:Class.method` |

Koszt to szacunek: tokeny z `usage` mnożone przez ceny z `pricing.json`. Dla nieznanego modelu, np. `auto`, koszt to `null`, a `request_summary.cost_complete` ma wartość `false`.

## Raport

```bash
cd backend
python -m observability.report            # tekst
python -m observability.report --json --since 2026-11-21T10:00
jq 'select(.event=="prompt_injection")' logs/app.jsonl
```

Raport podaje liczbę żądań, p50 i p95 czasu, koszt łączny i średni, tokeny dla każdego modelu, błędy wyszukiwania, injection według rodzaju i źródła, wstrzymania oraz czasy etapów.
