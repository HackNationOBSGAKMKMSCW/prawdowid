# Sprawdź.To (Prawdowid) - dokumentacja techniczna

<center><h3><a href="https://78-10-195-255.sslip.io">DEMO</a></h3></center> <br>
<center><b><a href="https://78-10-195-255.sslip.io/admin/login">DEMO ADMIN</a></b></center> <br> <br>

OPIS
Zespół: Interpoland

Sprawdź.to - zweryfikuj informacje tak łatwo, jak wysłasz wiadomość

PROBLEM

Pogłoski i „przekazane dalej” wiadomości rozchodzą się w komunikatorach szybciej, niż ktokolwiek zdąży je sprawdzić. Zwykły obywatel nie zna metod weryfikacji i nie będzie instalował narzędzi. Prawdowid działa jak wiadomość do znajomego: wklejasz tekst lub link i dostajesz prostą odpowiedź po polsku, ze stwierdzeniami, werdyktem i linkami do źródeł.

CO ODRÓŻNIA NASZE ROZWIĄZANIE

1. Dowody zamiast gładkich zdań. Model nie jest źródłem prawdy. Służy do rozumienia tekstu i wyodrębniania twierdzeń, a werdykt opiera się na wynikach z zewnętrznego źródła: Google Fact Check Tools, czyli ocenach organizacji fact-checkingowych. Każde twierdzenie jest sprawdzane osobno i równolegle.
2. Uczciwość wobec niepewności. Przy braku danych system nie zgaduje, tylko zwraca „niezweryfikowane”. Gdy oceny się różnią (np. „prawda” i „fałsz”), jawnie zgłasza konflikt zamiast udawać pewność.
3. Jedna logika, wiele kanałów. Interfejs WWW (React/Vite) i demonstrator WhatsApp (adapter FastAPI zgodny z kształtem webhooków WhatsApp Cloud API) korzystają z tych samych modułów, bez duplikowania logiki. Symulator obsługuje tekst, przyciski, listy, interaktywne karty werdyktu, odpowiedzi ze źródłami, streaming postępu i ostrzeżenie dla wiadomości przekazanych dalej.
4. Usługa, nie skrypt. Niezależne moduły (analiza tekstu, odpytywanie źródeł, pobieranie artykułów, obserwowalność) i wymienny model przez API zgodne z OpenAI ograniczają zależność od jednego dostawcy. Gotowe są też klienty dane.gov.pl, EUR-Lex i Sejm/API ELI, pokryte testami, do podłączenia kolejnych źródeł urzędowych.
5. Dostępność dla osób z niepełnosprawnościami. Funkcja czytania na głos, wysokiego kontrastu.

PRZEPŁYW

Tekst lub URL → sanityzacja → (dla URL) pobranie i oczyszczenie artykułu (Trafilatura) → analiza modelem → walidacja schematu (Pydantic) → wyodrębnienie twierdzeń i słów kluczowych → równoległe sprawdzenie w Google Fact Check → agregacja do statusu → zwięzła odpowiedź ze źródłami.

BEZPIECZEŃSTWO (wbudowane od początku)

- Treść użytkownika jest w prompcie oznaczona jako niezaufane dane, a wynik wymuszony do schematu JSON z dozwolonymi kategoriami.
- Heurystyczne wykrywanie prompt injection oraz token canary w wyjściu: wykrycie wycieku zeruje część wyniku i ustawia ostrzeżenia.
- Ochrona SSRF przy pobieraniu URL (tylko HTTP/HTTPS, blokada adresów prywatnych, loopback i link-local)

---
  
## 1. Przegląd

**Sprawdź.To** to serwis do weryfikacji informacji po polsku. Użytkownik wkleja wiadomość albo link na stronie WWW lub wysyła ją botowi WhatsApp.
Serwis:

1. wyciąga z tekstu twierdzenia, słowa kluczowe i frazy wyszukiwania (LLM),
2. szuka dowodów w API publicznych (Google Fact Check, dane.gov.pl, EUR-Lex, Sejm) i na stronach z białej listy (gov.pl, fact-checkerzy),
3. pobiera pełne artykuły,
4. zwraca **dwie niezależne oceny**:
   1. **werdykt dla każdego twierdzenia** (potwierdzone / fałsz / wprowadzające w błąd / brak danych / niesprawdzalne) z dosłownymi cytatami ze źródeł,
   2. **analizę wiadomości**: techniki manipulacji (kategorie A–G) i spójność dat,
5. oznacza twierdzenia znane z bazy EUvsDisinfo jako zweryfikowaną rosyjską dezinformację.

Administracja widzi ruch, alerty, luki informacyjne i zagrożenia w osobnym panelu.

**Stos technologiczny**

| Warstwa        | Technologie                                                  |
| -------------- | ------------------------------------------------------------ |
| Backend        | Python 3.14 (3.13 działa), FastAPI, uvicorn, httpx, pydantic v2, psycopg 3 / asyncpg |
| LLM            | klient `openai` do dowolnego endpointu zgodnego z API OpenAI (domyślnie model `gemini-3.5-flash-lite`) |
| Analiza tekstu | dateparser, rapidfuzz, własny BM25, trafilatura + lxml (pobieranie artykułów) |
| Baza           | PostgreSQL (konta, dziennik, listy); SQLite jako tryb zapasowy panelu bez `DATABASE_URL` |
| Frontend       | Vite 8, React 19, TypeScript (strona na porcie 5173, panel na 5175) |
| Wdrożenie      | backend jako usługa (Render), strona i panel na Vercel (`vercel.json`) |

## 2. Architektura

Cały backend to **jeden proces FastAPI** (`backend/server.py`, obiekt `server:app`), który obsługuje stronę, panel admina i kanał WhatsApp.

```
przeglądarka (frontend/)            bot WhatsApp / symulator
   │ GET /api/check                    │ POST /api/whatsapp/webhook
	-----------------------------------
	                   |
					   ▼  
 server:app  (backend/server.py)
 ├─ api_routes.py         /api/check, /api/check/{id}/report, /api/health
 ├─ public_sources.py     /api/trusted-sources (publiczna lista z bazy)
 ├─ admin/ + accounts/    /api/admin/*  (panel, konta, dziennik, zagrożenia)
 └─ whatsappAdapter       /api/whatsapp/*
        │
        ▼  verification.start(text)
 textAnalysis ─► (apiReading ∥ trustedSources) ─► articleScraping
      │                                                         │
      └─► knownDisinfo (równolegle, od razu po twierdzeniach)---|
                                                                |
			----------------------------------------------------
 			|     
      		▼ 			   ┌─ inputDataAnalysis ─► "input_analysis"
         evidence ───────►┤
                          └─ prawdowid_analysis ─► "claims_verdict"
                               (+ nadpisanie z EUvsDisinfo)
                                             │
                                             ▼  api_adapter.to_check_response  →  CheckResponse (JSON dla strony)


PostgreSQL: konta, tokeny, strony zaufane, dziennik zapytań i działań, zgłoszenia
Logi: backend/logs/app.jsonl → panel: Logi techniczne, Zagrożenia
```

**Warstwy middleware** (od zewnętrznej): `ObservabilityMiddleware` (request\_id, nagłówek `X-Request-ID`) → `CORSMiddleware` (tylko `GET/POST/OPTIONS`, adresy z `CORS_ORIGINS`) → `RequestSizeLimitMiddleware` (96 KiB) → `SqlInjectionAuditMiddleware` (skan żądań w osobnym wątku, zgłoszenia do panelu) → trasy.

**Zasady projektowe widoczne w kodzie**

- *Izolacja błędów.* Każdy etap zwraca zdarzenie ze statusem `ok` albo `error`; awaria jednej oceny nie psuje drugiej.
- *Model nie ma ostatniego słowa.* Werdykt wymaga dosłownego cytatu z istniejącego źródła; kod obniża werdykt bez pokrycia do „brak danych”.
- *Wstrzykiwanie zależności.* `create_app(...)` i `verification.Stages` przyjmują podmieniane implementacje (testy bez sieci, kluczy i bazy).
- *Prywatność.* Wyniki sprawdzeń nie są zapisywane w całości; użytkownicy są dla panelu tylko pseudonimami (HMAC).

## 3. Struktura repozytorium

| Katalog         | Zawartość                                                    |
| --------------- | ------------------------------------------------------------ |
| `backend/`      | API i cała logika serwisu (moduły niżej), `server.py`, `pipeline.py`, `api_*.py`, skrypty w `scripts/` |
| `analysis/`     | `inputDataAnalysis` (manipulacje, daty), `prawdowid_analysis` (werdykt), korpus testowy `data/`, ewaluacja `scripts/eval_verdict.py` |
| `frontend/`     | strona dla obywateli (React) oraz symulator WhatsApp (`/whatsapp`) |
| `admin_panel/`  | frontend panelu admina (React) i pierwotny kontrakt `openapi.yaml` |
| `whatsapp_sim/` | adapter WhatsApp (router FastAPI dołączany do `server:app`)  |
| `docs/`         | dokumentacja serwisu, koszty i skalowanie, plany funkcji (`plans/`) |
| katalog główny  | `requirements*.txt`, `pytest.ini`, `ruff.toml`, `vercel.json`, `.env.example`, `URUCHOMIENIE.md` |

Moduły w `backend/`:

| Moduł               | Rola                                                         |
| ------------------- | ------------------------------------------------------------ |
| `textAnalysis`      | ekstrakcja twierdzeń, słów kluczowych, zapytań; filtr prompt injection |
| `apiReading`        | klienci zewnętrznych API (fact-check, prawo, dane otwarte)   |
| `trustedSources`    | wyszukiwanie wyłącznie na stronach z białej listy            |
| `knownDisinfo`      | dopasowanie do bazy EUvsDisinfo przez serwer MCP             |
| `articleScraping`   | pobieranie pełnych artykułów, ochrona SSRF                   |
| `verification`      | spina etapy w zadanie z trzema zdarzeniami                   |
| `admin`, `accounts` | panel, monitor zapytań, alerty, konta, role, dziennik działań |
| `database`          | połączenie, migracje, CLI `python -m database`               |
| `observability`     | logi JSON, pomiar etapów i kosztów LLM, wykrywanie prompt injection |

## 4. Przebieg jednego sprawdzenia

`GET /api/check?text=…` (`backend/api_routes.py`) wykonuje kolejno:

1. **Limit równoległości.** Semafor `MAX_CONCURRENT_CHECKS` (domyślnie 4). Gdy zajęty, natychmiast `503 analysis_busy` (bez kolejki).
2. **Rozpoznanie wejścia.** Samo URL (`http(s)://…` bez spacji) jest walidowane (`validate_url`), rozwiązywane w DNS (limit 5 s) i odrzucane, jeśli wskazuje na adres niepubliczny (`unsafe_url`). Tekst zaczynający się od URL, ale z dodatkowymi słowami, to `invalid_url`.
3. **Ekran dziennika panelu** (`CheckJournal.screen`): blokada użytkownika (`403 user_blocked`), treści o wysokim ryzyku (`422 request_refused`), zapis zapytania.
4. **Weryfikacja** (`verification.start`) pod limitem `CHECK_TIMEOUT_SECONDS` (360 s).
5. **Adapter odpowiedzi** (`api_adapter.to_check_response`) zamienia raport na `CheckResponse`.
6. **Zapis**: dziennik panelu (`journal.complete`) i identyfikator wyniku w `api_check_results` (potrzebny do zgłoszeń). Odpowiedź ma nagłówki `Cache-Control: no-store` i `Referrer-Policy: no-referrer`.

Wewnątrz `verification.start` (`backend/verification/service.py`):

1. `analyze` → `textAnalysis.run`. Dla samego URL artykuł jest najpierw pobierany i dopiero jego tekst analizowany (`pipeline.analyze_input`). Gdy analizator nie wyodrębni twierdzeń, **cały tekst (do 1000 znaków) jest sprawdzany jako jedno twierdzenie**, chyba że wykryto ostrzeżenia bezpieczeństwa.
2. Równolegle od razu po twierdzeniach startuje `knownDisinfo` (nie czeka na resztę).
3. **Evidence**: `apiReading.run` ∥ `trustedSources.run`, potem `articleScraping.run`.
4. Po zebraniu materiałów **dwie oceny startują razem i nie czekają na siebie**:
   - `input_analysis` → `inputDataAnalysis.analyze_async` (timeout 240 s),
   - `claims_verdict` → `prawdowid_analysis.pipeline.run`, a potem nałożenie trafień z EUvsDisinfo.
5. Błędy: awaria jednej oceny to jej zdarzenie `error`; brak materiałów kończy obie ocenę błędem `evidence_failed`. Jeśli werdykt padnie, a baza EUvsDisinfo ma trafienia, zdarzenie i tak jest `ok` (trafienia są rozstrzygające, pozostałe twierdzenia dostają `blad_analizy`).

`VerificationEvent`: `request_id`, `part` (`evidence` | `input_analysis` | `claims_verdict`), `status`, `data`, `error{kind,message}`, `duration_ms`, `finished_at`. Zadanie można zużyć jako strumień (`verification.stream`), osobne części (`start`) albo wszystko naraz (`run`). CLI: `python -m verification "tekst"` (`--jsonl`).

## 5. Moduły backendu

### 5.1 `textAnalysis`

Jedno wywołanie LLM zwraca kategorię tematu, kod języka, pewność, uzasadnienie, **słowa kluczowe** (maks. 25), **twierdzenia** (maks. 40) i **frazy wyszukiwania** (maks. 8, do 120 znaków). Odpowiedź jest walidowana schematem pydantic; za długie listy są przycinane, a nie odrzucane. Wynik trafia do kontenera `AnalysisDataContainer` (`source_text`, `statements`, `search_queries`, `keywords`, `security_warnings`, `started_at`…). Wejście przechodzi przez `InputSanitizer` (wykrywanie prompt injection); kontener ma `is_safe` (brak ostrzeżeń) i `is_confident(threshold=0.75)`. Osobny model dla tego etapu: `TEXT_ANALYSIS_MODEL`.

### 5.2 `apiReading`

Klienci dziedziczą po `BaseApiClient` (wspólne żądania, ponowienia, pomiar). Rejestr wybiera klientów według **kategorii** (`FACT_CHECK`, `LEGAL_ACT`, `LEGISLATIVE_PROCESS`, `OPEN_DATA`, `NEWS`, `OFFICIAL`, `ARTICLE_EXTRACT`). Klienta można wyłączyć z panelu (`API_READING_DISABLED_CLIENTS`).

| Klient (`name`)     | Kategoria             | Źródło                                                      |
| ------------------- | --------------------- | ----------------------------------------------------------- |
| `google_fact_check` | `FACT_CHECK`          | Google Fact Check Tools (klucz `GOOGLE_FACT_CHECK_API_KEY`) |
| `eurlex`            | `LEGAL_ACT`           | EUR-Lex (SPARQL)                                            |
| `sejm_eli`          | `LEGAL_ACT`           | ELI Sejmu (akty prawne)                                     |
| `sejm`              | `LEGISLATIVE_PROCESS` | API Sejmu (procesy legislacyjne)                            |
| `dane_gov`          | `OPEN_DATA`           | dane.gov.pl                                                 |

`run(analysis)` zwraca po jednym wyniku na twierdzenie, a potem wyniki **krótkich fraz** (maks. 8): Google Fact Check dopasowuje krótkie frazy, nie całe zdania. Wyniki fraz tworzą wspólną pulę dla werdyktu. `run_full_text` odpytuje API pełnym tekstem (używa go m.in. bot WhatsApp).

### 5.3 `trustedSources`

Biała lista (ok. 50 wpisów w `whitelist.py`; w działaniu lista z tabeli `trusted_sources`, edytowana w panelu). Moduł **nigdy nie rzuca wyjątku**, błędy źródeł trafiają do `report.failures`. Typ każdej strony jest wykrywany automatycznie (`detect.py`) w kolejności: gov.pl → fact-checker → feed → listing → sitemap → reference.

| Adapter                | Jak szuka                                                    |
| ---------------------- | ------------------------------------------------------------ |
| `govpl_search`         | API wyszukiwarki gov.pl, zawsze zawężone do serwisu z listy  |
| `fact_check_publisher` | Google Fact Check z filtrem wydawcy (Demagog, Konkret24, AFP, fakenews.pl) |
| `feed`                 | ostatnie wpisy z RSS/Atom (cache)                            |
| `listing`              | linki i tytuły ze strony-listy artykułów (cache)             |
| `sitemap`              | tylko najnowsze pod-sitemapy (maks. 3, z 90 dni)             |
| `reference`            | sam link „sprawdź na bieżąco” dla paneli i map (IMGW, GIOŚ)  |

Dopasowanie (`ranking.py`): normalizacja bez polskich znaków i prosty stemmer, wymóg pokrycia słów zapytania, ranking BM25 z bonusem za fact-checkera i świeżość. Cache `TRUSTED_SOURCE_CACHE_TTL` (1200 s), timeout `TRUSTED_SOURCE_TIMEOUT` (6 s). CLI: `python -m trustedSources list | check --all | search "…" | warm`.

### 5.4 `knownDisinfo`

Sprawdza, czy twierdzenie jest w bazie **EUvsDisinfo** (ponad 19 tys. przypadków), przez serwer MCP (`https://mcp.euvsd.info/mcp`, klucz w nagłówku `X-API-Key`). Przebieg: LLM tworzy 1–3 angielskie zapytania na twierdzenie → MCP `search` (tylko wpisy `claim_review`, maks. 5 kandydatów) → LLM-sędzia wskazuje przypadek będący **tą samą tezą** albo `null`. Zasada ostrożności: niepewność, temat bez tej samej tezy, identyfikator spoza kandydatów albo błąd modelu dają brak trafienia i ostrzeżenie. `run()` nie rzuca wyjątków; zwraca `DisinfoCheck` ze statusem `ok` | `disabled` (brak klucza) | `error`.

### 5.5 `articleScraping`

Pobiera pełne artykuły z trzech źródeł: `user_text` (linki od użytkownika, maks. `ARTICLE_MAX_USER_LINKS`=2), `fact_check`, `trusted_source`. Limity: `ARTICLE_MAX_LINKS`=5, współbieżność 1, `ARTICLE_BATCH_TIMEOUT`=60 s, tekst do 50 000 znaków. Wymaga **co najmniej 2 różnych stron** (host bez `www.`; na gov.pl liczy się osobno każdy serwis) — pobiera linki zapasowe, ale nie sięga po strony niezwiązane z tezą; wynik niesie `distinct_sites` i `min_sites_met`. Ekstraktor: `local` (fetch + trafilatura, bez opłat) albo `diffbot` (token). **Ochrona SSRF**: `url_validation.py` + `safe_http.py` (rozwiązywanie DNS, odrzucanie adresów niepublicznych, kontrola przekierowań).

### 5.6 `verification`

Opisany w sekcji 4. Dodatkowo `disinfo.py` nakłada trafienia EUvsDisinfo na werdykt: trafione twierdzenie dostaje `verdict: falsz`, etykietę „Zweryfikowana rosyjska dezinformacja”, pewność wysoką, pole `known_disinformation` (tytuł, url, opis, uzasadnienie), przypadek jako pierwszy dowód i wpis w `adjustments`; werdykt całego tekstu jest liczony od nowa. `mapping.py` przekazuje obu ocenom te same artykuły pod tymi samymi identyfikatorami (`art1`, `art2`…).

## 6. Moduł `analysis/`

### 6.1 Werdykt (`prawdowid_analysis`)

> **Uwaga:** w bieżącym lokalnym `main` kod Pythona tego pakietu jest usunięty (patrz sekcja 15); poniższy opis pochodzi z ostatniej wersji w historii (`0ffdf6a^`) oraz z `analysis/README.md`.

Dla każdego twierdzenia model dostaje wyłącznie **źródła wzorcowe**:

- wpisy fact-checkingowe znalezione dla tego twierdzenia (maks. 5),
- pasujące wpisy ze wspólnej puli fraz (BM25, wymagane wspólne słowo),
- fragmenty korpusu `data/sources` (BM25, top 5) — **w backendzie wyłączone** (`use_corpus=False`, bo korpus to przykłady testowe),
- artykuły pobrane przez `articleScraping` (top 5 fragmentów).

Wynik BM25 jest mnożony przez **premię za aktualność** względem *daty zdarzenia* z twierdzenia (nie daty zapytania). Źródło starsze niż `VERDICT_MAX_SOURCE_AGE_DAYS` (730) to `material_archiwalny` dla tego twierdzenia.

Przebieg dla jednego twierdzenia (`verdict.py`):

1. brak źródeł → deterministycznie `brak_wystarczajacych_danych` (bez wywołania modelu),
2. prompt systemowy z regułami **R1–R17** (`prompts/werdykt_system.md`) + `<claim>`, `<source>`, opcjonalnie `<context>` (nigdy jako dowód),
3. odpowiedź musi być JSON zgodnym z `ModelVerdict`; jedna szansa na poprawkę,
4. wyciek *canary* z promptu unieważnia odpowiedź,
5. niespójność (werdykt bez dosłownego cytatu) → jedna runda naprawcza,
6. **kontrola deterministyczna** (`checks.py`): cytat musi występować dosłownie w źródle; `prawda`/`falsz` bez zweryfikowanego dowodu lub przy sprzeczności są obniżane; rozstrzygnięcie tylko na fact-checkach ma pewność ≤ „średnia”; tylko na materiale archiwalnym — flaga `werdykt_na_materiale_archiwalnym`; każda zmiana trafia do `adjustments`,
7. awaria techniczna lub dwie błędne odpowiedzi → `blad_analizy` (nigdy udawany werdykt).

**Werdykty twierdzenia:** `prawda`, `falsz`, `brak_wystarczajacych_danych`, `blad_analizy`. **Werdykt tekstu** (`aggregate.py`, bez LLM): wszystkie `prawda` → `prawdziwy`; wszystkie `falsz` → `falszywy`; choć jeden `falsz` → `zawiera_falsz`; choć jedna `prawda` → `czesciowo_potwierdzony`; same błędy → `blad_analizy`; brak twierdzeń → `nieweryfikowalny`; reszta → `brak_wystarczajacych_danych`.

**Ochrona przed prompt injection** (`security.py`): normalizacja NFKC i usuwanie znaków niewidocznych, wykrywanie poleceń dla modelu (PL/EN), **kwarantanna źródeł** z wstrzyknięciem, oznaczanie podejrzanych twierdzeń, neutralizacja znaczników w prompcie, canary. Ewaluacja: `data/eval/cases.json` (55 przypadków, w tym 11 prób injection), skrypt `scripts/eval_verdict.py`; wynik zapisany w README: 55/55 na `gemini-3.5-flash-lite`.

Konfiguracja (`config.py`): `FREELLM_*`, `VERDICT_JSON_MODE`, `VERDICT_CONCURRENCY` (3), `VERDICT_MAX_SOURCE_AGE_DAYS` (730); starsze nazwy `OPENAI_*`/`LLM_MODEL` są przepisywane na `FREELLM_*`.

### 6.2 Analiza wiadomości (`inputDataAnalysis`)

`analyze_async(user_input, sources, article_date)` uruchamia równolegle dwie analizy.

**Manipulacja** (`manipulation.py`, `resources/taxonomy.json`): LLM wskazuje fragmenty tekstu według taksonomii, a kod lokalizuje je w tekście (`spans.py`) i liczy wynik 0–100 (`score_fragments`, skala 3,0 — przy ok. 3 ważonych fragmentach na 100 słów wynik ≈ 63).

| Litera | Kod                  | Kategoria          |
| ------ | -------------------- | ------------------ |
| A      | `EMOTIONAL_LANGUAGE` | język emocjonalny  |
| B      | `FEAR_APPEAL`        | straszenie         |
| C      | `CONSPIRACY_FRAMING` | sugerowanie spisku |
| D      | `FALSE_URGENCY`      | fałszywa pilność   |
| E      | `LACK_OF_SOURCE`     | brak źródła        |
| F      | `EXAGGERATION`       | wyolbrzymienie     |
| G      | `CHERRY_PICKING`     | cherry-picking     |

**Spójność dat** (`temporal.py`, `dates.py`): LLM tylko wyciąga daty i dopasowuje je do źródeł; normalizacja do przedziałów `[start, end]`, wyrażenia względne („w środę”, „w ubiegłym miesiącu”), reguły i opisy są **deterministyczne** (testy bez API). Progi: tolerancja 1 dzień, duża rozbieżność 30 dni, „stare” po 365 dniach; okres bieżący zależy od kategorii (`breaking` 3 dni, `political_legal` 30, `economic` 365, `other` 30). Wynik: `dates_consistent`, lista `issues` (kod, ważność low/medium/high, `delta_days`, opis) i `extracted`.

## 7. Kontrakt API strony

Pełny opis i przykłady: `backend/API.md`; dokumentacja interaktywna pod `/docs`, `/redoc`, `/openapi.json`.

| Metoda i ścieżka                         | Opis                                                         |
| ---------------------------------------- | ------------------------------------------------------------ |
| `GET /api/check?text=` (1–15 000 znaków) | pełna analiza tekstu albo samego linku                       |
| `POST /api/check/{id}/report`            | zgłoszenie błędu: `reason` ∈ `wrong_verdict`, `bad_source`, `misunderstood`, `other`, opcjonalny `comment` (≤ 1000 znaków); odpowiedź 204 |
| `GET /api/health`                        | gotowość, w tym połączenie z bazą                            |
| `GET /api/trusted-sources[/{id}]`        | publiczna lista włączonych stron zaufanych (bez bazy: `503 sources_unavailable`) |

**Odpowiedź `CheckResponse`:** `status: "result"`, `id`, `input_type` (`text` | `url`), `claims[]` (`verdict`, `text`, `explanation`, `sources[]` z `quote`, `publisher`, `url`, `year`, `lang`), `analysis` (`manipulation{manipulation_detected, score, fragments[]}`, `dates{dates_consistent, article_date, issues[], extracted[]}`), `source_names`.

**Mapowanie werdyktów** (`api_adapter.py`):

| Werdykt wewnętrzny                            | `claims[].verdict` w API |
| --------------------------------------------- | ------------------------ |
| `prawda`, `prawdziwy`                         | `confirmed`              |
| `falsz`, `falszywy`                           | `false`                  |
| `zawiera_falsz`, `czesciowo_potwierdzony`     | `misleading`             |
| `brak_wystarczajacych_danych`, `blad_analizy` | `insufficient`           |
| `nieweryfikowalny`                            | `unverifiable`           |

**Błędy** mają postać `{"error": {"code", "message"}, "request_id"}` (trasy panelu zwracają `{"detail": …}`):

| Kod HTTP | `code`                                                       | Przyczyna                                                    |
| -------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| 422      | `invalid_request`, `invalid_url`, `unsafe_url`, `url_unavailable` | złe dane wejściowe lub adres niepubliczny                    |
| 422      | `request_refused`                                            | prośba o szkodliwe instrukcje (broń, materiały wybuchowe, CBRN) |
| 403      | `user_blocked`                                               | klient zablokowany w panelu                                  |
| 404      | `result_not_found`                                           | zgłoszenie do nieistniejącego lub wygasłego wyniku           |
| 502      | `analysis_failed`, `invalid_analysis_result`                 | awaria etapu analizy                                         |
| 503      | `analysis_busy`, `storage_unavailable`                       | przeciążenie lub baza niedostępna                            |
| 504      | `analysis_timeout`                                           | przekroczono limit czasu                                     |
| 500      | `internal_error`                                             | nieoczekiwany błąd (szczegóły tylko w logu)                  |

Przy błędzie etapu do logu trafia tylko nazwa etapu i typ wyjątku — nigdy treść zapytania.

## 8. Panel admina i konta

Panel działa w **tym samym procesie** co API strony (`mount_admin` w `server.py`, prefiks `/api/admin`, wyłączany `ADMIN_PANEL=off`). Każde `/api/check` trafia do dziennika zapytań (kanał `web`), zgłoszenia błędów dopisują się do tego samego wpisu, a zmiany modeli i stron zaufanych działają bez restartu.

**Logowanie i sesje.** `POST /api/admin/auth/login` (e-mail + hasło konta z tabeli `users`) zwraca token sesji; każde żądanie poza `/health` i `/auth/login` wymaga `Authorization: Bearer <token>`. Hasła to skróty `scrypt`, tokeny są w bazie jako SHA-256 (sam sekret zna tylko przeglądarka), po kilku nieudanych próbach logowanie jest czasowo blokowane (429), zmiana hasła wylogowuje wszystkie sesje. Awaryjnie istnieje `ADMIN_API_TOKEN` (najlepiej nie ustawiać).

**Role** (`accounts/permissions.py`; backend egzekwuje uprawnienia, panel tylko chowa widoki):

| Rola      | Zakres                                                       |
| --------- | ------------------------------------------------------------ |
| `admin`   | pełna kontrola: modele i klucze, źródła, reguły i progi, blokady użytkowników, konta i hasła, dziennik audytu |
| `analyst` | tylko odczyt i eksport: pulpit, statystyki, alerty, luki, historia, logi, użytkownicy serwisu, źródła |
| `user`    | wewnętrzna rola konta serwisu (`checks:create`, `me:*`)      |

Rola `moderator` jest wyłączona (migracja `0007` zmieniła takie konta na analityków); wartość została w typie bazy. Token może mieć węższy zakres (`abilities`) niż rola, nigdy szerszy.

**Trasy `/api/admin`** (uprawnienie w nawiasie):

| Grupa            | Trasy                                                        |
| ---------------- | ------------------------------------------------------------ |
| Auth (`/auth/*`) | `login`, `logout`, `me`, `me/password`, `me/tokens`          |
| Konta            | `GET/POST /accounts`, `PATCH/DELETE /accounts/{id}`, `POST /accounts/{id}/password`, `GET /activity` (administrator) |
| Podgląd          | `dashboard`, `queries[/{id}]`, `users[/{key}]` + `block`/`unblock`, `alerts[/{id}]`, `info-gaps` (+ `summary`, `ranking`), `topics/{id}` |
| Bezpieczeństwo   | `threats` (prompt injection, ataki manipulacyjne, informacje krytyczne — z logów), `events`, `events/summary` (`security:read`) |
| Konfiguracja     | `GET/PATCH config`, `config/audit`, `config/models`, `maintenance/purge` |
| Źródła           | `GET/POST/PATCH/DELETE sources`, `sources/seed`, `sources/status`, `sources/check` |

**Monitor** (`admin/monitor.py`) przy każdym zapytaniu robi `screen` (blokady, treści wysokiego ryzyka, zapis), a po wyniku `complete` (twierdzenia, werdykty, luki, alerty). Awaria monitora nie przerywa rozmowy; `ADMIN_MONITOR=off` wyłącza rejestr.

**Alerty:** luka informacyjna, kampania dezinformacyjna, niebezpieczny użytkownik, prompt injection, rosyjska dezinformacja, SQL injection.

- *Luka informacyjna*: twierdzenie bez rozstrzygnięcia (`brak_wystarczajacych_danych`, `nieweryfikowalny` albo brak źródeł). Podobne twierdzenia są grupowane w tematy; w trybie `auto` próg to `info_gap_min_users` (domyślnie 3 użytkowników w 7 dni), w trybie `zapytania` — `info_gap_min_queries`.
- *Treści niebezpieczne* (`admin/safety.py`): poziomy `brak` / `sredni` (temat wrażliwy, np. pytanie o zamach z wiadomości) / `wysoki` (zamiar operacyjny: prośba o instrukcję, przepis, zdobycie połączona z niebezpiecznym tematem: terroryzm, materiały wybuchowe, broń, CBRN). Poziom wysoki daje `422 request_refused`.
- *SQL injection* (`admin/sqli.py`, `request_audit.py`): skan żądań w tle, zgłoszenie do panelu z kanałem `web`, `panel` lub `whatsapp`.

**Prywatność.** Użytkownicy serwisu są widoczni tylko jako pseudonim (HMAC z `ADMIN_USER_SALT`). Retencja: dziennik zapytań `monitoring.retention_days` (domyślnie 30), zgłoszenia `REPORT_RETENTION_DAYS` (180). Modele, klucze API i progi zmienia się w panelu (`PATCH /api/admin/config`, zapis w `RUNTIME_CONFIG_FILE`, z audytem w `config_audit`).

## 9. Baza danych

PostgreSQL (`DATABASE_URL`; API strony domyślnie wymaga zweryfikowanego SSL, lokalnie `DATABASE_SSL_MODE=disable`). Bez `DATABASE_URL` panel działa na SQLite (`ADMIN_DB_PATH`), ale bez kont. Migracje to pliki `backend/database/migrations/NNNN_nazwa.sql`; każda jest stosowana raz i zapisana w `schema_migrations` z sumą kontrolną — **edycja zastosowanej migracji jest błędem**.

| Migracja                      | Treść                                                      |
| ----------------------------- | ---------------------------------------------------------- |
| `0001_accounts`               | `users`, `auth_access_tokens`                              |
| `0002_trusted_sources`        | lista stron zaufanych                                      |
| `0003_activity_logs`          | dziennik działań (audyt)                                   |
| `0004_query_journal`          | dziennik zapytań użytkowników, twierdzenia, tematy, alerty |
| `0005_api_feedback`           | `api_check_results`, `api_check_reports`                   |
| `0006_query_reports`          | zgłoszenia w dzienniku panelu                              |
| `0007_disable_moderator_role` | konta moderatorów → analitycy                              |
| `0008_query_request_index`    | indeks po identyfikatorze żądania                          |
| `0009_info_gap_queries`       | luki informacyjne liczone po zapytaniach                   |

Główne tabele: `users`, `auth_access_tokens`, `trusted_sources`, `activity_logs`, `user_queries`, `query_claims`, `query_topics`, `end_users`, `monitor_alerts`, `config_audit`, `api_check_results`, `api_check_reports`, `schema_migrations`.

CLI (z katalogu `backend/`): `python -m database check | migrate | seed-sources | create-user --email … --name … --role admin`.

## 10. Obserwowalność i bezpieczeństwo

**Logi** (`observability`): JSON Lines w `backend/logs/app.jsonl` (rotacja 5 × 5 MB), każde żądanie ma `request_id` (nagłówek `X-Request-ID`). `init()` podmienia w runtime wybrane funkcje na wrappery, więc moduły nie wymagają zmian. Zdarzenia: `llm_call` (model, czas, tokeny, koszt wg `pricing.json`), `search_call`/`search_error`/`search_retry`, `prompt_injection`, `abstain`, `evidence_empty`, `stage` (czas etapu), `request_summary`. Konwencje dla nowych modułów: `backend/observability/NOWE_MODULY.md`. Nie loguje się pełnego tekstu użytkownika ani kluczy (formatter maskuje pola `*key*`, `token`, `authorization`).

**Warstwy ochrony widoczne w kodzie**

| Zagrożenie                           | Mechanizm                                                    |
| ------------------------------------ | ------------------------------------------------------------ |
| SSRF przez link użytkownika          | `url_validation.py`, `safe_http.py`: rozwiązanie DNS, odrzucenie adresów niepublicznych (również w `/api/check`: `unsafe_url`) |
| Prompt injection                     | `InputSanitizer` w `textAnalysis`, `security.py` w werdykcie (kwarantanna źródeł, canary), detektory w `inputDataAnalysis`, zdarzenia `prompt_injection` w panelu Zagrożenia |
| Halucynacje modelu                   | cytaty sprawdzane dosłownie, obniżanie werdyktów bez pokrycia, `blad_analizy` zamiast udawanego wyniku |
| Nadużycia i przeciążenie             | limit równoległych sprawdzeń (503), limit ciała żądania 96 KiB, `CHECK_TIMEOUT_SECONDS`, blokada użytkowników w panelu |
| SQL injection                        | audyt wszystkich żądań + alert w panelu                      |
| Treści szkodliwe                     | filtr `safety.py` (`request_refused`)                        |
| Wyciek danych w odpowiedziach błędów | ogólne komunikaty, szczegóły tylko w logu; `no-store`, `no-referrer` |
| Przeglądarka                         | CORS tylko dla `CORS_ORIGINS`, bez credentials, metody `GET/POST/OPTIONS` |

## 11. Kanał WhatsApp

Adapter `whatsapp_sim/backend/whatsappAdapter` jest częścią głównego backendu (`/api/whatsapp/*`, wyłączany `WHATSAPP_ENABLED=false`). Rozumie formaty **WhatsApp Cloud API** (webhook `whatsapp_business_account`) i odpowiada treściami, jakich oczekuje `POST /{phone-number-id}/messages`; po stronie „WhatsApp” jest symulator w przeglądarce (`/whatsapp`). Podłączenie prawdziwego numeru wymaga tylko transportu przekazującego webhooki Mety i wysyłającego odpowiedzi do Graph API.

```
symulator ── webhook ──▶ POST /api/whatsapp/webhook[?stream=true]
                      SprawdzToBot
                       ├─ monitor panelu: blokady, treści wysokiego ryzyka
                       ├─ verification.start(text)   (ta sama weryfikacja co /api/check)
                       └─ CheckResponse → karta werdyktu + szczegóły
        ◀── wiadomości ──  monitor panelu: wynik, luki, alerty
```

Pliki: `bot.py` (komendy `/clear`, powitania, pomoc), `pipeline.py`, `verdicts.py`, `formatting.py` i `verified_formatting.py` (zamiana wyniku na wiadomości), `cloud_api.py` (kształty Cloud API), `admin_bridge.py` (most do monitora), `server.py` (router). Tryby `SPRAWDZTO_MODE`: `live` (domyślnie, pełna weryfikacja), `factcheck` (tylko Google Fact Check, szybciej, ale może różnić się od strony), `demo` (przykładowe tematy bez sieci, każda odpowiedź oznaczona).

## 12. Aplikacje frontendowe

**Strona dla obywateli** (`frontend/`, React 19 + Vite, port 5173). Trasy: `/` (sprawdzanie: ekrany Start → Sprawdzanie → Wynik / Stan), `/zrodla` (lista stron zaufanych z `/api/trusted-sources`), `/pomoc`, `/deklaracja-dostepnosci`, `/whatsapp` (symulator). Kod: `src/api/` (klient `client.ts`, atrapa `mock.ts`, typy zgodne z `CheckResponse`), `src/components/` (karty twierdzeń i analizy, okno zgłoszenia błędu), `src/lib/` (m.in. odczyt na głos, komunikaty dla czytników ekranu, udostępnianie, preferencje). **Tryby:** `VITE_API_MODE=mock` (domyślnie, żadnych zapytań do backendu, czarny pasek „DEMO”) i `live` (`npm run dev:live`). `VITE_CHECK_TIMEOUT_MS` musi odpowiadać `CHECK_TIMEOUT_SECONDS`.

**Panel admina** (`admin_panel/frontend`, React 19 + Vite, port 5175). Widoki w `src/pages/`: Pulpit, Statystyki, Alerty, Luki informacyjne, Powtarzające się zapytania, Historia sprawdzeń, Źródła i strony zaufane, Modele, Reguły i progi, Konfiguracja, Użytkownicy (konta) i Użytkownicy serwisu, Dziennik audytu, Logi techniczne, Zagrożenia, Bezpieczeństwo. Warstwa danych (`src/api/`) ma dwie implementacje wybierane w konfiguracji: **backend** (`http.ts`, `backend/mappers.ts`) i **demo** (`mock/`, konta `admin@sprawdz.to.demo` / `analityk@sprawdz.to.demo`, hasło `demo1234`, uruchomienie `npm run dev:demo`). Adres API ustawia `public/config.json`.

## 13. Konfiguracja

Wspólny `.env` w katalogu głównym (wzór: `.env.example`; starszy `backend/.env` jest czytany jako zapas, zmienne ze środowiska mają pierwszeństwo).

| Grupa                | Zmienne                                                      |
| -------------------- | ------------------------------------------------------------ |
| Model                | `FREELLM_API_KEY`, `FREELLM_BASE_URL`, `FREELLM_MODEL`, `FREELLM_TIMEOUT` (60), `FREELLM_MAX_RETRIES` (2), `TEXT_ANALYSIS_MODEL`, `VERDICT_JSON_MODE`, `VERDICT_CONCURRENCY` (3), `VERDICT_MAX_SOURCE_AGE_DAYS` (730), `LLM_TIMEOUT`, `LLM_TEMPERATURE`, `LLM_MAX_RETRIES` |
| Źródła               | `GOOGLE_FACT_CHECK_API_KEY`, `EUvsDisinfo_API_KEY`, `EUVSDISINFO_MCP_URL`, `KNOWN_DISINFO_ENABLED`, `KNOWN_DISINFO_MAX_CANDIDATES` (5), `TRUSTED_SOURCE_TIMEOUT` (6), `TRUSTED_SOURCE_CACHE_TTL` (1200) |
| Artykuły             | `ARTICLE_EXTRACTOR` (`local`/`diffbot`), `DIFFBOT_API_TOKEN`, `ARTICLE_SCRAPING_ENABLED`, `ARTICLE_MAX_CONCURRENCY` (1), `ARTICLE_MAX_LINKS` (5), `ARTICLE_MAX_USER_LINKS` (2), `ARTICLE_BATCH_TIMEOUT` (60) |
| Baza                 | `DATABASE_URL`, `DATABASE_SSL_MODE`, `DATABASE_SCHEMA`, `ACCOUNTS_REGISTRATION` (`open`/`closed`) |
| API                  | `CORS_ORIGINS`, `CHECK_TIMEOUT_SECONDS` (360), `MAX_CONCURRENT_CHECKS` (4), `REPORT_RETENTION_DAYS` (180) |
| Panel                | `ADMIN_PANEL`, `ADMIN_MONITOR`, `ADMIN_USER_SALT`, `ADMIN_API_TOKEN`, `ADMIN_DB_PATH`, `ADMIN_STORE`, `RUNTIME_CONFIG_FILE`, `API_READING_DISABLED_CLIENTS` |
| Logi                 | `LOG_ENABLED`, `LOG_LEVEL`, `LOG_FILE`, `LOG_CONSOLE`, `LOG_PRICING_FILE`, `LOG_TRACE_TARGETS` |
| Kanały i frontend    | `WHATSAPP_ENABLED`, `SPRAWDZTO_MODE`, `VITE_API_MODE`, `VITE_API_BASE_URL`, `VITE_CHECK_TIMEOUT_MS`, `VITE_DEMO_BAR`, `VITE_WHATSAPP_NUMBER`, `API_PROXY_TARGET`, `ADMIN_API_PROXY_TARGET` |
| Lokalizacja pakietów | `PRAWDOWID_ANALYSIS_DIR` (domyślnie katalog `analysis/`)     |

## 14. Uruchomienie, testy i wdrożenie

Pełna instrukcja: `URUCHOMIENIE.md`. Skrót (z katalogu głównego; Windows: `.venv\Scripts\python`):

```bash
python -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
cp .env.example .env     # uzupełnij FREELLM_*, GOOGLE_FACT_CHECK_API_KEY, DATABASE_URL
(cd backend && ../.venv/bin/python -m database migrate && ../.venv/bin/python -m database seed-sources)
(cd backend && ../.venv/bin/python -m database create-user --email admin@example.pl --name "Jan Kowalski" --role admin)

PYTHONPATH=backend:analysis:analysis/src .venv/bin/uvicorn server:app --port 8000   # API + panel + WhatsApp
npm --prefix frontend run dev:live                                                  # http://localhost:5173
npm --prefix admin_panel/frontend run dev                                           # http://localhost:5175
```

Sprawdzenie: `http://127.0.0.1:8000/api/health` zwraca `{"status":"ok"}`.

**Testy.** `pytest.ini` obejmuje `backend` i `analysis` (`asyncio_mode = auto`, znacznik `live` do testów z prawdziwymi API pomijany domyślnie). W archiwum jest ok. 35 plików testowych backendu, 23 w `analysis/` i 6 w adapterze WhatsApp; testy działają bez kluczy i bazy (atrapy LLM i sieci, `verification.Stages`, `tests/fakes.py`, fixtures JSON). `analysis/tests/test_backend_contract.py` pilnuje zgodności z formatem backendu. Frontendy nie mają testów automatycznych. Komendy: `python -m pytest backend`, `cd analysis && python -m pytest`, ewaluacja na prawdziwym modelu: `python -m scripts.eval_verdict`; jakość kodu: `ruff` (`ruff.toml`), Prettier/oxlint we frontendach.

**Skrypty** (`backend/scripts`): `estimate_llm_tokens.py` (pomiar tokenów na jedno sprawdzenie z atrapą modelu), `load_test.py` (test obciążeniowy API), `smoke_pipeline.py` (przejście całego potoku).

**Wdrożenie.** Backend jako osobna usługa (build `pip install -r requirements.txt`, start `uvicorn server:app --host 0.0.0.0 --port $PORT`, `PYTHONPATH=backend:analysis:analysis/src`, `CORS_ORIGINS=https://<domena>`); strona i panel na Vercel jednym projektem z `vercel.json` (strona pod `/`, panel pod `/admin`). **W `vercel.json` trzeba podmienić `TWOJ-BACKEND.onrender.com`** na adres backendu. Strona i WhatsApp łączą się z backendem bezpośrednio (stad CORS), bo jedno sprawdzenie trwa do kilku minut, a przekierowania Vercel mają limit 120 s; panel idzie przez przekierowanie `/api/admin`.

## 15. Uwagi z przeglądu kodu

Poniższe punkty wynikają z analizy statycznej archiwum (testy nie były uruchamiane).

**Krytyczne**

1. **Brak kodu pakietu `prawdowid_analysis`.** Commit `0ffdf6a` („zmiana nazwy”, 22.11.2026) usunął z `analysis/src/prawdowid_analysis` wszystkie pliki Pythona (`pipeline.py`, `verdict.py`, `checks.py`, `security.py`, `schemas.py` i inne); został katalog `prompts/` oraz `egg-info`. Backend nadal importuje pakiet (`verification/_analysis.py`), więc `claims_verdict` kończy się błędem `AnalysisUnavailable` (poza twierdzeniami z trafień EUvsDisinfo), a testy w `analysis/tests` powinny się nie importować. Ostatnia pełna wersja jest w `0ffdf6a^` oraz w gałęzi `origin/analiza-zadania`. Wcześniej zauważył to też `docs/dokumentacja-serwisu.md` (sekcja 8). Decyzja: przywrócić pakiet (`git checkout 0ffdf6a^ -- analysis/src/prawdowid_analysis`) albo przenieść go pod nową nazwę i poprawić importy.
2. **Pliki wrażliwe w archiwum.** Zip zawiera `analysis/.env` (nie otwierałem go; może zawierać klucze), a także `backend/logs/app.jsonl`, `analysis/outputs/*.json` oraz katalogi `.venv`, `node_modules` i `.git` (ok. 260 MB). Przed udostępnieniem archiwum dalej warto usunąć te elementy i rozważyć rotację kluczy, jeśli `.env` je zawiera.

**Do uporządkowania**

3. **Nazwa produktu:** w kodzie, pakietach i repozytorium `prawdowid`/`SprawdzTo`, w interfejsie i API „Sprawdź.To” (domeny demo `sprawdz.to.demo`).
4. **Nieaktualne opisy w README:** `trustedSources/README.md` mówi o liście tylko w kodzie, a w działaniu lista pochodzi z bazy; `admin/README.md` opisuje SQLite jako domyślny rejestr, a z `DATABASE_URL` używany jest PostgreSQL; `admin_panel/README.md` wspomina o sprawach moderatora, choć rola jest wyłączona; `backend/API.md` odsyła do `render.yaml`, którego nie ma w archiwum; `whatsapp_sim/README.md` jest po angielsku.
5. **Ograniczenia znane z `docs/dokumentacja-serwisu.md`:** kanał WhatsApp bez limitu równoległych sprawdzeń i bez limitu zapytań na osobę; logi w lokalnym pliku procesu (panel Zagrożenia widzi tylko jedną instancję).
6. **Brak testów frontendów** (strona i panel).
7. **`GET /api/check?text=`** umieszcza treść w adresie URL; aplikacja jej nie loguje, ale pośrednicy (proxy, platforma) mogą zapisywać adresy.
8. **Korpus `analysis/data/sources`** to przykłady do testów, dlatego backend wywołuje werdykt z `use_corpus=False`; w produkcji źródłem dowodów są wyłącznie API, strony zaufane i pobrane artykuły.

## 16. Koszty i skalowanie (skrót)

Szczegóły i metodyka: `docs/koszty-i-skalowanie.md`.

| Miara                                                        | Wartość                                                      |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| Wywołania LLM na jedno sprawdzenie                           | 4–8 (twierdzenia, manipulacje, daty, 1 werdykt na twierdzenie, ew. EUvsDisinfo) |
| Koszt modelu na 1000 sprawdzeń (typowa wiadomość, 3 twierdzenia) | ok. 18–20 USD (z buforowaniem stałej części promptów ok. 15 USD) |
| Stałe utrzymanie (strona, panel, API, baza)                  | ok. 45–90 USD/mies.                                          |
| Przepustowość jednego procesu                                | 4 równoległe sprawdzenia, ok. 360–720/h przy 20–40 s na sprawdzenie |
| Zachowanie powyżej limitu                                    | natychmiastowe `503 analysis_busy`, bez kolejki              |
| Darmowy klucz Gemini                                         | ok. 2 sprawdzenia/min i ok. 80/dobę, nie nadaje się do produkcji |

## 17. Jak rozszerzać system

- **Nowe API zewnętrzne:** klasa dziedzicząca po `BaseApiClient` z polami `name` i `supported_categories`, dopisana do `CLIENT_CLASSES` w `apiReading/clients/__init__.py`; rejestr podpina ją automatycznie do kategorii. Testy z fixture JSON w `apiReading/tests/fixtures`.
- **Nowa strona zaufana:** wpis w panelu (Źródła i strony zaufane) albo `whitelist.py` + `python -m database seed-sources`; dla paneli i map podaj `topics`. Typ strony można wymusić polem `adapter`.
- **Nowa migracja:** nowy plik `NNNN_nazwa.sql` z unikalnym numerem; nigdy nie edytuj zastosowanej.
- **Nowy moduł w potoku:** dodać etap do `verification.Stages` (z domyślnymi implementacjami i atrapami w testach) oraz oznaczyć go w logach (`@traced("modul.etap")`, `NOWE_MODULY.md`).
- **Nowy typ alertu lub reguła:** `admin/monitor.py` (stany tematu i progi w sekcji `monitoring` konfiguracji) wraz z opisem w panelu (`pages/RulesPage.tsx`, `ThresholdsPage.tsx`).
