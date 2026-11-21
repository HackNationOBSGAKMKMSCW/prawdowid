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
- **Runda naprawcza** (`verdict.py`): gdy odpowiedź modelu jest niespójna (werdykt bez
  pasującego dosłownego cytatu, cytat spoza źródła), model dostaje jedną szansę na
  poprawkę z opisem problemu; poprawiona odpowiedź i tak przechodzi kontrolę.
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
.venv/Scripts/python -m prawdowid_analysis.cli --backend --fact-checks pelny-tekst "Tekst"
.venv/Scripts/python -m scripts.eval_verdict                      # ewaluacja na prawdziwym modelu
```

Kody wyjścia CLI: `0` – sukces, `2` – brak konfiguracji modelu, `3` – błąd backendu.

## Integracja z backendem

Z kodu (np. z backendu):

```python
from prawdowid_analysis.pipeline import run

analysis = await textAnalysis.run(text)
per_statement = await apiReading.run(analysis)  # lista wyników
full_text = await apiReading.run_full_text(analysis)  # jeden wynik
verdict = await run(analysis, [*per_statement, full_text])  # TextVerdict
print(verdict.model_dump_json(indent=2))
```

- **Wejście**: `run()` przyjmuje `AnalysisDataContainer` (lub słownik po `to_dict()`)
  oraz wyniki `apiReading.run()`, `apiReading.run_full_text()`, ich połączenie albo
  słowniki po `model_dump()`. Adapter czyta pola, nie importuje backendu.
- **Fact-checki**: wyniki zapytań o konkretne stwierdzenie trafiają do tego
  stwierdzenia; pozostałe (np. pełny tekst) tworzą wspólną pulę, z której każde
  twierdzenie dostaje pasujące wpisy (BM25). Format `payload` rozpoznawany jest po
  `item.source`: `google_fact_check` i (wstępnie, wg planu) `euvsdisinfo`; wpisy
  innych dostawców są pomijane z ostrzeżeniem.
- **Dane z `textAnalysis`**: `keywords` uzupełniają zapytanie BM25, `language_code`
  wywołuje ostrzeżenie przy tekście w innym języku niż korpus, a fragment
  `source_text` trafia do modelu jako `<context>` – tylko do interpretacji
  twierdzenia, nigdy jako dowód (reguła R17). Kontekst z podejrzaną treścią jest
  pomijany.
- **Linki do źródeł z wejścia** (`input_sources`): każde źródło od użytkownika i każdy
  wpis fact-checkingowy z backendu – także te, które nie pasowały do żadnego
  twierdzenia – z `url`, wydawcą, oceną i statusem: `cytowane` (dowód w werdykcie,
  `cited_in_claims`), `pokazane_modelowi` (`shown_for_claims`), `nieuzyte` albo
  `kwarantanna`. Cytowane fragmenty: `cited_quotes`; link także w
  `claims[].evidence[].url`.
- **Ostrzeżenia** (`warnings`): błędy dostawców raz, po polsku i z liczbą zapytań
  (np. brak `GOOGLE_FACT_CHECK_API_KEY`), obcięte zapytanie pełnym tekstem,
  nieobsługiwani dostawcy, różnica języka.
- **Konfiguracja**: zmienne procesu → `analysis/.env` → `backend/.env`. Starsze nazwy
  (`OPENAI_API_KEY`, `LLM_MODEL`…) są przepisywane na `FREELLM_*`, a `--backend`
  ładuje konfigurację przed importem backendu, więc ekstrakcja stwierdzeń i werdykt
  używają tego samego modelu. Wynik zawiera `models` per etap.
- **Zgodność**: `tests/test_backend_contract.py` przepuszcza przez potok prawdziwe
  obiekty backendu i zapisany fixture; zmiana formatu w backendzie wywraca test.
  Odświeżenie fixture: `python -m tests.backend_objects`.

## Źródła wzorcowe

- `data/sources/*.json` – lokalny korpus (`id`, `title`, `publisher`, `url`,
  `published_at`, `text`). Obecne pliki to **przykłady do testów**; docelowo trzeba
  je zastąpić zatwierdzonymi źródłami z prawdziwymi adresami URL.
- Wyniki `apiReading` (Google Fact Check) – krótkie wpisy z oceną fact-checkera;
  werdykt oparty tylko na nich ma najwyżej pewność `srednia`.
- `--sources` / `extra_sources` – źródła podane w zapytaniu.

## Aktualność źródeł i materiał archiwalny

- **Data odniesienia** (`claims[].reference_date`, `reference_basis`): wiek źródła liczymy
  względem CZASU ZDARZENIA, którego dotyczy twierdzenie, a nie chwili wpłynięcia zapytania.
  Data pochodzi z treści twierdzenia („w 2014 roku” → 2014-12-31, „1 maja 2004”,
  „w kwietniu 2026” → koniec miesiąca, najpóźniejsza z wymienionych). Twierdzenie o stanie
  obecnym („obecnie”, „dziś”…) albo bez daty → dzień analizy.
- **Wiek** (`age_days`) = dni od publikacji do daty odniesienia; wartość ujemna oznacza
  źródło opublikowane po zdarzeniu (relację) – nie jest stare.
- **Limit** `VERDICT_MAX_SOURCE_AGE_DAYS` (domyślnie 730 dni): źródło opublikowane wcześniej
  niż limit PRZED datą odniesienia jest `material_archiwalny` względem tego twierdzenia.
  To samo źródło może być archiwalne dla „obecnie…”, a aktualne dla „w 2014 roku…”.
  Wiek i flagi per twierdzenie: `claims[].source_freshness[]` i `claims[].evidence[]`;
  `input_sources[].archival_for_claims` mówi, dla których twierdzeń źródło jest archiwalne.
  Na listach globalnych (`sources`, `input_sources`) są tylko cechy niezależne od
  twierdzenia: `brak_daty_publikacji`, `data_publikacji_w_przyszlosci`.
- **Znaczniki czasu**: `published_at` (publikacja) i `fetched_at` (pobranie:
  `ReadingResult.fetched_at` z backendu, pole `fetched_at` w korpusie i w pliku `--sources`;
  źródło z zapytania bez znacznika dostaje czas analizy). Wynik zawiera `analyzed_at`
  i `max_source_age_days`.
- **Preferowanie aktualnych danych**: wynik BM25 jest mnożony przez premię za bliskość
  zdarzeniu (1 dla źródła z dnia zdarzenia lub późniejszego, 0,5 na granicy limitu), więc
  z równie trafnych źródeł wygrywa bliższe zdarzeniu. Model dostaje datę analizy, datę
  odniesienia twierdzenia, wiek źródeł i atrybut `archival="tak"`; reguła R11 każe przy
  zmianach stanu rzeczy preferować najnowsze źródło, a twierdzenie oparte wyłącznie na
  materiale archiwalnym oceniać jako brak danych.
- **Ostrzeżenia i flagi**: ostrzeżenie `Tn: źródło [...] to materiał archiwalny…` podaje
  datę publikacji, wiek, datę odniesienia i jej podstawę. Twierdzenie dostaje
  `freshness_flags`: `zrodla_archiwalne` i `werdykt_na_materiale_archiwalnym` (dowody
  rozstrzygające wyłącznie archiwalne – pewność najwyżej `srednia`).
- **Kontrola**: gdy model odrzuca aktualne źródło jako „nieaktualne” (o aktualności
  rozstrzyga wyłącznie limit), runda naprawcza prosi go o ponowną ocenę.

## Metadane źródeł w JSON

| Miejsce | tytuł | wydawca | data publikacji / pobrania | link | cytowany fragment |
|---|---|---|---|---|---|
| `claims[].evidence[]` | `source_title` | `publisher` | `published_at` | `url` | `quote` (zweryfikowany dosłownie) |
| `input_sources[]` | `title` | `publisher` | `published_at` / `fetched_at` | `url` | `cited_quotes[]` (per twierdzenie) |
| `sources[]` | `title` | `publisher` | `published_at` / `fetched_at` | `url` | – (cytaty są w dowodach) |
| `quarantined_sources[]` | `title` | `publisher` | `published_at` / `fetched_at` | `url` | – (nie trafia do modelu) |

`claims[].sources_reviewed[]` ma tylko `source_id`, `relevant`, `why` – metadane źródła są
w `sources[]` pod tym samym `source_id`. Pola `title`/`source_title`, `publisher`,
`published_at`, `url` i `quote` są zawsze obecne (jako `null`, gdy źródło ich nie ma):
przykładowe dokumenty korpusu (`data/sources/`) nie mają `url` – przy zastępowaniu ich
prawdziwymi źródłami trzeba podać adres. Cytat istnieje tylko dla źródeł użytych jako
dowód (przy „brak danych” dowodów zwykle nie ma).

### Skrócona odpowiedź (domyślnie)

CLI wypisuje wynik skrócony przez `output.compact()` (ok. 43% krótszy na teście
end-to-end): bez pełnej treści źródeł, kontekstu tekstu użytkownika, powtórzonych
metadanych (`sources_reviewed`, `source_freshness` tylko dla źródeł z flagą
aktualności), drobnych duplikatów (`verdict_label`, `source_ids`, `model` przy
twierdzeniu, `model_verdict` równy `verdict`) i pól pustych. Pełny wynik:
`--pelny`; z kodu – `TextVerdict.model_dump()`, skrócony – `compact(verdict)`.

## Ochrona przed prompt injection

Ochrona nie polega wyłącznie na posłuszeństwie modelu; warstwy po stronie kodu:

1. **Czyszczenie** (`security.clean_text`): normalizacja NFKC (znaczniki pełnej
   szerokości `＜/source＞` stają się wykrywalne), usunięcie znaków zerowej
   szerokości, sterujących kierunkiem tekstu i kontrolnych, limity długości.
2. **Wykrywanie** (`security.detect_injection`): polecenia dla modelu („zignoruj
   instrukcje”, „oceń jako prawdę”), udawane komunikaty systemowe, zmiana roli,
   próby wycieku promptu, podszywanie się pod znaczniki `<claim>`/`<source>`,
   gotowe odpowiedzi JSON, podważanie innych źródeł – po polsku i angielsku.
3. **Kwarantanna źródeł**: źródło (korpus, użytkownik, fact-check) z wykrytym
   wstrzyknięciem nie trafia do modelu i nie może być dowodem; wynik pokazuje je
   w `quarantined_sources` i `warnings`.
4. **Oznaczanie twierdzeń**: podejrzane twierdzenie jest oceniane (to przedmiot
   weryfikacji), ale model dostaje ostrzeżenie, a wynik ma `security_warnings`.
5. **Prompt**: dane w `<claim>`/`<source>` po neutralizacji znaczników, reguła R3,
   przypomnienie na końcu wiadomości, identyfikator-pułapka (canary) – jego
   pojawienie się w odpowiedzi unieważnia ją.
6. **Kontrola wyniku**: werdykt wymaga dosłownego cytatu z istniejącego źródła,
   więc model nie przemyci rozstrzygnięcia spoza danych.

## Ewaluacja

`data/eval/cases.json` – 55 przypadków w kategoriach: fakty, liczby, daty, negacja,
brak danych (w tym opinie i prognozy), źródła użytkownika, sprzeczności, aktualność,
fact-checki oraz 11 prób prompt injection (w twierdzeniu, w źródłach, we wpisie
fact-checkingowym, znaczniki pełnej szerokości, próby wycieku promptu).
Przypadek może określić własne źródła, dopuszczalne (`accept`) i zabronione
(`forbidden`) werdykty; skrypt raportuje naruszenia bezpieczeństwa.

Wynik na `gemini-3.5-flash-lite` (prompt `werdykt-v1-e7e671b9`): **55/55**,
0 naruszeń bezpieczeństwa, 6/6 zatrutych źródeł w kwarantannie. Przy wielu
przebiegach pod rząd dostawca może odcinać zapytania (`RateLimitError` →
`blad_analizy`); wtedy pomaga `VERDICT_CONCURRENCY=1` i ponowienie wybranych id:
`python -m scripts.eval_verdict E28 E29 …`.
