# SYNC 2: werdykty na atrapie i ocena pasaży (osoba B)

Data: 2026-11-21. LLM: FreeLLMAPI, `LLM_MODEL=auto` (router wybiera model; faktyczny model
z nagłówka `x-routed-via`). Odtworzenie:

```bash
.venv/Scripts/python scripts/verdict_demo.py                  # atrapa (rag/mock.py)
.venv/Scripts/python scripts/verdict_demo.py --source sample  # sample_input.json, chunking A
```

`--source sample` tnie `data/samples/sample_input.json` funkcją `build_payloads` osoby A
(pasaże jak w Qdrancie, `CHUNK_CHARS=800`) i wybiera top-k prostym rankingiem po tokenach
z `rag/sparse.py`. Qdrant nie jest potrzebny. Pełny wynik (`AnalysisOutput`) trafia do
`outputs/` (gitignored).

## Jak działają reguły (pełne `rules.py`)

| Sytuacja | Wynik |
| --- | --- |
| awaria LLM / retrievera / brak klucza | status `error` (nigdy werdykt) |
| opinia, `check_worthy=false` | `not_verifiable` (bez wywołania LLM) |
| brak dowodu z cytatem zweryfikowanym w źródle | `insufficient_evidence` + przekazanie |
| źródła T1–T2 po obu stronach | `insufficient_evidence` + `conflicting_sources` |
| ≥ 2 niezależne T1–T2 potwierdzają | `confirmed` |
| ≥ 2 niezależne T1–T2 obalają | `false` |
| 1 źródło T1–T2 albo same media (T3) | `insufficient_evidence` + przekazanie |

- Ranga: T1 = `official_primary`, `public_data`, `research`; T2 = `fact_check`,
  `news_agency`; T3 = `media` (nie liczy się do progu).
- Niezależność = różni wydawcy. Kilka dokumentów lub pasaży jednego wydawcy liczy się raz.
- `quote_verified=false` nie wspiera werdyktu. Dowód bez znanego pasażu też nie.
- Siła z jawnych czynników: `high` przy ≥ 3 niezależnych T1–T2 albo ≥ 2 z T1, bez
  sprzeczności, nieaktualnych źródeł i braków dat; `medium` przy spełnionym progu z
  zastrzeżeniem; `low` poniżej progu.
- `stale_source`: źródło starsze niż próg dla typu twierdzenia (liczby i wydarzenia 365 dni,
  prawo 730, nauka 1825, cytaty bez progu).

## Wyniki

**Atrapa** (4 twierdzenia, k=4, 16 wywołań): 1× `false` (siła `high`: urząd + fact-check),
3× `insufficient_evidence`. Twierdzenie „paszport w jeden dzień” wspiera tylko komentarz
medialny (T3), starszy niż rok, więc nie dostaje werdyktu i ma flagę `stale_source`.
Wcześniejszy szkielet dawał tu `confirmed`. Dokument z próbą wstrzyknięcia nie zmienił
oceny innych pasaży.

**Dane przykładowe A** (7 twierdzeń, k=4, 19 wywołań): 1× `false` (`high`), 1× `not_verifiable`
(opinia), 5× `insufficient_evidence`.

| Metryka | Atrapa | Dane A |
| --- | --- | --- |
| długość pasaży (min/mediana/max, zn.) | 65/132/168 | 181/379/763 |
| pasaże bez `published_at` | 0 | 0 |
| cytaty zweryfikowane / rozstrzygające stanowiska | 5/5 | 7/7 |
| cytat jako część pasażu (mediana) | 54% | 19% |
| zły JSON (fallback) | 1/16 (przed poprawką parsera) | 0/19 |
| tokeny wejścia na wywołanie (mediana) | 465 | 594 |
| czas wywołania LLM (mediana / max) | 0,3 s / 3,5 s | 0,4 s / 55 s |
| czas na twierdzenie (mediana) | 3,7 s | 1,2 s |

## Czy pasaże wystarczają do stance i cytatów? Wnioski do ustalenia z A

1. **Długość: tak.** Przy pasażach do ~800 znaków model wskazuje krótki, dosłowny cytat (19%
   pasażu), a weryfikacja go odnajduje (7/7). Nie trzeba skracać pasaży. Pasaże dłuższe niż
   ~1500 znaków warto sprawdzić osobno, bo rośnie koszt tokenów.
2. **Metadane: wystarczają.** `source_type`, `publisher` i `published_at` są we wszystkich
   pasażach i wystarczają do rangi, niezależności i aktualności. Prośba do A: zachować
   `published_at` przy każdym dokumencie (brak daty obniża siłę werdyktu).
3. **Najczęstszy wynik to `insufficient_evidence`, bo w danych jest jedno źródło na temat.**
   Reguła „min. 2 niezależne T1–T2” jest spełniona tylko dla opłaty paszportowej. Prośba
   do A: w `sample_input.json` i zbiorze testowym dodać drugie niezależne źródło T1–T2 dla
   części twierdzeń (np. świadczenie 800 zł, PM10, szczepionka), żeby testować `confirmed`
   i `false`.
4. **Nakładające się pasaże jednego dokumentu** (np. `_c0` i `_c1` po overlapie zdania) dają
   powtórzone dowody. Reguły liczą je raz (ten sam wydawca), ale to dodatkowe wywołanie LLM.
   Do rozważenia: retriever zwraca najwyżej 1–2 pasaże na dokument.
5. **`misleading` jeszcze nie jest przyznawany.** Przykład: „szczepionka zmniejsza
   hospitalizacje o połowę”, a badanie podaje 38%. Model dał `refutes`, a uczciwszy werdykt
   to „wprowadza w błąd”. Kontrakt stanowiska (supports/refutes/neutral/insufficient) nie ma
   wartości „częściowo prawda / brak kontekstu”. Propozycja zmiany kontraktu do decyzji
   zespołu (PR do `CONTRACTS.md`): dodać `partially_supports` albo flagę `missing_context`
   w dowodzie.
6. **Czas: mediana mieści się w celu (≤ 30 s), ale przy `auto` zdarzają się skrajne
   przypadki** (jedno wywołanie 55 s, gdy router trafił na wolniejszy model). Opcje: przypiąć
   model albo `auto:fast` na demo i ewaluację, równoległe wywołania stance dla pasaży jednego
   twierdzenia, limit czasu na wywołanie.
7. **Przy `auto` modele zmieniają się między wywołaniami** (4 różne w jednym przebiegu), więc
   wyniki ewaluacji nie będą powtarzalne. Do ewaluacji przypiąć model.
