# Logowanie w nowym module

Przewodnik dla osób, które dopisują nowy moduł: kolejne źródło danych, nowy etap pipeline'u, kanał (np. REST API, Telegram) albo nowy model. Opis całego pakietu jest w [README.md](README.md).

## 1. Co dostajesz za darmo

Po `init()` część rzeczy loguje się sama, bez żadnego kodu po Twojej stronie:

| Jeśli Twój moduł… | Logowane jest automatycznie |
|---|---|
| woła model przez SDK `openai` (`chat.completions.create/parse`, `responses.create`), z dowolnym `base_url`, np. Gemini | `llm_call`: model, tokeny, koszt, czas, błąd |
| pobiera dane przez klienta dziedziczącego po `apiReading.base.BaseApiClient` | `search_call`, `search_error`, `search_retry` |
| czyści wejście przez `textAnalysis.analysis.InputSanitizer.sanitize` | `prompt_injection` |
| działa wewnątrz żądania HTTP z `ObservabilityMiddleware` albo w funkcji oznaczonej `@traced` | wszystkie zdarzenia dostają wspólne `request_id`, a na końcu pojawia się `request_summary` |

Jeśli moduł spełnia te warunki, zostaje tylko krok 2 (czas etapów) i krok 6 (wstrzymania).

## 2. Czas etapów: `@traced`

Oznacz główne funkcje modułu, czyli to, co woła reszta aplikacji:

```python
from observability import traced

@traced("telegramAdapter.check")      # nazwa: <moduł>.<etap>
async def check(text: str) -> Report:
    ...
```

Dekorator działa dla funkcji i metod, synchronicznych i asynchronicznych. Loguje `stage` z `duration_ms`, `ok` i `error`. Wyjątki przepuszcza dalej bez zmian. Jeśli funkcja zostanie wywołana poza żądaniem (CLI, skrypt, test), sama otwiera żądanie i na koniec zapisuje `request_summary`.

Dla krótkiego fragmentu wewnątrz funkcji użyj `with stage("modul.krok"): ...`.

Jeśli nie chcesz importować `observability` w swoim kodzie, możesz dodać cel z zewnątrz na dwa sposoby:
- **Na próbę:** zmienną środowiskową `LOG_TRACE_TARGETS="pakiet.modul:funkcja=nazwa,pakiet.modul:Klasa.metoda"`.
- **Na stałe:** jedną linią w `STAGE_TARGETS` w [instrument.py](instrument.py): `StageTarget("pakiet.modul", "Klasa.metoda", "pakiet.etap")`. Jeśli moduł zniknie albo zmieni nazwę, cel zostanie pominięty i aplikacja zadziała dalej.

## 3. Nowy punkt startowy (serwer, bot, CLI)

```python
from observability import ObservabilityMiddleware, init

init()                                        # raz, jak najwcześniej, przed importem reszty modułów
app = FastAPI()
app.add_middleware(ObservabilityMiddleware)   # jedno żądanie HTTP = jedno request_id
```

W skrypcie albo w kolejce zadań, gdzie nie ma HTTP, granicę żądania wyznacz ręcznie:

```python
from observability import request_scope

with request_scope("worker.job", request_id=job.id):
    await process(job)
```

Uwaga przy `python -m pakiet.modul`: kod pliku uruchomionego jako `__main__` to inna kopia modułu niż ta, którą podmienia instrumentacja. Po `init()` zaimportuj funkcję startową przez nazwę modułu, tak jak na końcu `textAnalysis/analysis.py`.

## 4. Model LLM spoza SDK `openai`

Przy innym SDK albo surowym HTTP zaloguj wywołanie sam, dzięki temu tokeny i koszt trafią do podsumowania żądania:

```python
import time
from types import SimpleNamespace
from observability.instrument import record_llm_call

started = time.perf_counter()
kwargs = {"model": "gemini-2.5-flash-lite"}
try:
    raw = await call_my_model(prompt)
except Exception as exc:
    record_llm_call(api="custom", kwargs=kwargs, started=started, error=exc)
    raise
usage = SimpleNamespace(prompt_tokens=raw["in_tokens"], completion_tokens=raw["out_tokens"])
record_llm_call(api="custom", kwargs=kwargs, started=started,
                response=SimpleNamespace(model=kwargs["model"], usage=usage))
```

Nowy model dopisz do [pricing.json](pricing.json) jako cenę w USD za 1M tokenów. Klucz wystarczy jako fragment nazwy, wygrywa najdłuższe dopasowanie. Bez tego koszt będzie `null`, a `cost_complete` będzie `false`.

## 5. Nowe źródło danych / wyszukiwarka

**Najlepiej** napisz klienta jako podklasę `BaseApiClient` i nie nadpisuj `_request`. Wtedy wywołania, błędy i ponowienia logują się same.

Gdy to niemożliwe, loguj tymi samymi nazwami zdarzeń, żeby raport je policzył:

```python
from observability import current, log_event

metrics = current()
if metrics:
    metrics.add(search_calls=1)
try:
    response = await client.get(url)
except Exception as exc:
    if metrics:
        metrics.add(search_errors=1)
    log_event("search_error", level="warning", provider="moje_zrodlo",
              error=type(exc).__name__, status_code=getattr(exc, "status_code", None))
    raise
log_event("search_call", provider="moje_zrodlo", status_code=response.status_code)
```

Nie loguj `str(exc)` ani URL-a. Często zawierają klucz API.

Gdy wyszukiwanie zwróci zero wyników, zapisz `log_event("evidence_empty", level="warning", reason="no_results")`.

## 6. Wstrzymanie werdyktu (abstain)

Wszędzie tam, gdzie system **nie wydaje oceny** (timeout, brak źródeł, błąd, blokada bezpieczeństwa), dodaj jedną linię tuż obok kodu, który wybiera odpowiedź „nie wiem / spróbuj później”:

```python
from observability import log_abstain

except TimeoutError:
    log_abstain("timeout", channel="telegram")
    return TIMEOUT_TEXT
```

Powody, których już używamy (trzymaj się ich, nowe dodawaj w `snake_case`): `timeout`, `not_configured`, `analysis_failed`, `pipeline_error`, `search_failed`, `blocked_security`, `verdict_no_data`, `verdict_unverified`. Ten sam powód zgłoszony dwa razy w jednym żądaniu zapisuje się raz.

## 7. Nowe niezaufane wejście (scenariusz E)

Każdy tekst z zewnątrz (wiadomość użytkownika, treść strony, dokument, odpowiedź API wklejana do promptu) sprawdź przed wysłaniem do modelu. Możesz użyć `InputSanitizer.sanitize`, który loguje się sam, albo detektora z pakietu:

```python
from observability import log_prompt_injection
from observability.injection import scan

hit = scan(text)
if hit:
    log_prompt_injection(text=text, pattern=hit.pattern, snippet=hit.snippet,
                         source="telegram_message",          # skąd przyszedł tekst
                         kind="input_pattern")               # albo "indirect_source" dla treści stron/dokumentów
```

Logowane są tylko hash, długość i fragment do 80 znaków. Zgłoszenie tego samego tekstu dwa razy w żądaniu daje jeden wpis.

Do wykrywania przejęcia odpowiedzi modelu (np. kanarek w odpowiedzi, kategoria spoza listy) użyj `kind="system_prompt_leak"` albo `kind="output_hijack_suspected"` z `source="llm_output"`.

## 8. Własne zdarzenia

```python
from observability import log_event
log_event("cache_hit", provider="diffbot", age_s=120)
```

- Nazwa zdarzenia w `snake_case`, rzeczownik albo `rzecz_stan`. Najpierw sprawdź, czy taka nazwa już istnieje (tabela w README).
- Pola mają być płaskie i krótkie: liczby, kody, identyfikatory. `request_id` i bieżący etap dodają się same.
- **Nigdy** nie loguj pełnego tekstu użytkownika, treści artykułów, kluczy ani nagłówków. Do opisu tekstu służy `text_fingerprint(text)`, który daje hash i długość.
- `log_event` nigdy nie rzuca wyjątku. Błąd w logowaniu nie zepsuje żądania.
- Zwykłe komunikaty diagnostyczne loguj przez `logging.getLogger(__name__)` zamiast `print`. One też trafiają do `app.jsonl` z `request_id`.

## 9. Test i sprawdzenie

```python
import json, observability

def test_my_stage_is_logged(tmp_path):
    path = tmp_path / "app.jsonl"
    observability.init(log_file=path, console=False, instrument=False)
    try:
        my_module.check_sync("tekst")
        events = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
        assert any(e["event"] == "stage" and e["stage_name"] == "myModule.check" for e in events)
    finally:
        observability.shutdown()
```

Więcej gotowych wzorców jest w [tests/test_observability.py](tests/test_observability.py).

Ręcznie: uruchom moduł z `LOG_CONSOLE=true`, a potem sprawdź:

```bash
cd backend
python -c "import observability as o; o.init(); print(o.status())"   # czy Twoje cele są 'applied'
python -m observability.report
```

## Checklista dla nowego modułu

- [ ] Główne funkcje mają `@traced("modul.etap")` albo wpis w `STAGE_TARGETS`.
- [ ] LLM przez SDK `openai`, a jeśli nie, to `record_llm_call`. Model jest w `pricing.json`.
- [ ] Zewnętrzne API przez `BaseApiClient`, a jeśli nie, to `search_call`/`search_error`.
- [ ] Każde miejsce bez werdyktu ma `log_abstain("powód")`.
- [ ] Każde niezaufane wejście przechodzi przez `InputSanitizer` albo `scan()`.
- [ ] Nowy punkt startowy wywołuje `init()` i ma middleware albo `request_scope`.
- [ ] Brak pełnych tekstów i sekretów w polach zdarzeń, brak nowych `print`.
