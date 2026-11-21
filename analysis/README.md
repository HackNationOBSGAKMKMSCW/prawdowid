# Werdykt prawdziwości (`analysis/`)

Moduł ocenia, czy twierdzenia z tekstu są prawdziwe, porównując je **wyłącznie ze
źródłami wzorcowymi**. Zwraca szczegółowy werdykt w JSON: jakie źródła widział model,
na jakich dosłownych cytatach się oparł i czego brakuje, gdy danych jest za mało.

## Przepływ

```
tekst ──► stwierdzenia ──► źródła wzorcowe dla twierdzenia ──► LLM (prompt R1–R16, JSON)
          (textAnalysis     (fact-checki z apiReading,           │
           albo podział      korpus data/sources + BM25,         ▼
           na zdania)        źródła podane w zapytaniu)    kontrola deterministyczna
                                                           (cytaty, reguły werdyktu)
                                                                 │
                                                                 ▼
                                                  werdykt zbiorczy tekstu (JSON)
```

- **Prompt**: [`prompts/werdykt_system.md`](src/prawdowid_analysis/prompts/werdykt_system.md).
  Reguły R1–R16 są powiązane z założeniami w `prompts/__init__.py` (`REQUIREMENTS`),
  a test `tests/test_prompts.py` pilnuje, żeby żadna reguła nie zniknęła.
- **Werdykty twierdzenia**: `prawda`, `falsz`, `brak_wystarczajacych_danych`
  (plus `blad_analizy` przy awarii technicznej – nigdy udawany werdykt).
- **Kontrola** (`checks.py`): każdy cytat musi dosłownie występować we wskazanym
  źródle; `prawda`/`falsz` bez zweryfikowanego cytatu albo przy sprzeczności są
  obniżane do `brak_wystarczajacych_danych`. Każda korekta trafia do `adjustments`.
- **Werdykt tekstu** (`aggregate.py`): `prawdziwy`, `falszywy`, `zawiera_falsz`,
  `czesciowo_potwierdzony`, `brak_wystarczajacych_danych`, `nieweryfikowalny`, `blad_analizy`.

## Uruchomienie

```bash
cd analysis
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
cp .env.example .env          # uzupełnij FREELLM_API_KEY, FREELLM_BASE_URL, FREELLM_MODEL

.venv/Scripts/python -m pytest                                   # testy offline (atrapa LLM)
.venv/Scripts/python -m prawdowid_analysis.cli "Polska jest w UE od 2004 roku."
.venv/Scripts/python -m prawdowid_analysis.cli --sources moje.json "Tekst"
.venv/Scripts/python -m prawdowid_analysis.cli --backend "Tekst"  # z textAnalysis + apiReading
.venv/Scripts/python -m scripts.eval_verdict                      # ewaluacja na prawdziwym modelu
```

Z kodu (np. z backendu):

```python
from prawdowid_analysis.pipeline import run

analysis = await textAnalysis.run(text)
reading = await apiReading.run(analysis)
verdict = await run(analysis, reading)  # TextVerdict
print(verdict.model_dump_json(indent=2))
```

## Źródła wzorcowe

- `data/sources/*.json` – lokalny korpus (`id`, `title`, `publisher`, `url`,
  `published_at`, `text`). Obecne pliki to **przykłady do testów**; docelowo trzeba
  je zastąpić zatwierdzonymi źródłami z prawdziwymi adresami URL.
- Wyniki `apiReading` (Google Fact Check) – krótkie wpisy z oceną fact-checkera;
  werdykt oparty tylko na nich ma najwyżej pewność `srednia`.
- `--sources` / `extra_sources` – źródła podane w zapytaniu.

## Ewaluacja

`data/eval/cases.json` – 15 przypadków (prawda, fałsz, brak danych, opinia,
twierdzenie częściowo fałszywe, próba wstrzyknięcia instrukcji). Wynik pierwszego
uruchomienia na `gemini-3.5-flash-lite`: 15/15, bez korekt kontroli.
