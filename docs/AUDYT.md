# Audyt zgodności z zadaniem MSZ „Prawdowid”

Stan na 22.11.2026, branch `audit-01`, commit bazowy `b65e31d`. Każdy wiersz ma dowód w
kodzie (plik:linia) albo odwołanie do zmierzonego wyniku w [`docs/wyniki-testow/`](wyniki-testow/).
Numery W1–W31 odpowiadają liście napraw na końcu dokumentu.

Statusy: ✅ jest · 🟡 częściowo · ❌ brak · ⚪ świadomie pominięte (decyzja zespołu).

## 1. Podsumowanie

### Warunek brzegowy (sekcja 8)

Bez tych czterech pozycji funkcje premiowane dostają 0 punktów.

| Wymaganie | Status | Dlaczego |
|---|---|---|
| Działanie E2E bez ręcznej ingerencji | 🟡 | 20/20 zapytań tekstowych kończy się wynikiem bez ingerencji ([e2e_pelny](wyniki-testow/e2e_pelny_20261122_070054.md)); URL z długim artykułem (U01, Wikipedia) kończy się 504 po 270 s. Dziennik nie domyka sprawdzeń z „brak danych” (W29) |
| Brak sfabrykowanych źródeł | ❌ | Niezweryfikowane cytaty trafiają do UI (W1). Artykuł zgłoszony przez użytkownika może być dowodem sam dla siebie (W3). Dopasowanie do EUvsDisinfo nadpisuje werdykt cytatem oznaczonym jako zweryfikowany bez sprawdzenia (W2) |
| Poprawne wstrzymanie się przy braku dowodów | 🟡 | Warstwa werdyktu: 95% (18/19). E2E: 3/4 przypadków D; T12 (zmyślony przyszły zakaz gotówki) dostał „fałsz” |
| Dwa kanały (WWW + adapter) | 🟡 | Symulator WhatsApp korzysta z tej samej weryfikacji (`whatsapp_sim/backend/whatsappAdapter/pipeline.py:99-123`); kanał jest w przebudowie (⚪ W10) |
| Ryzyko dla demo u jury | ❌ | Auto-blokada po 2 groźnych zapytaniach jest liczona po IP; za proxy wszyscy mają jeden IP, więc blokada wyłącza stronę dla wszystkich (W21) |

### Mierniki obowiązkowe (sekcja 6)

Zmierzone na lokalnym `gemma4:26b-a4b`. Szczegóły i komendy do odtworzenia są w
[`docs/wyniki-testow/README.md`](wyniki-testow/README.md).

| Miernik | Cel | Warstwa werdyktu (63 przyp.) | Pełna ścieżka E2E (25 zapytań) |
|---|---|---|---|
| Macro-F1 (3 klasy obsługiwane) | ≥ 0,75 | ✅ 0,98 | n/d (brak etykiet dla wielu twierdzeń) |
| Pokrycie cytowań | ≥ 95% | ✅ 100% (44/44) | n/d (przebieg przerwany; treści odpowiedzi niezapisane) |
| Poprawność cytowań | ≥ 85% | ⏳ ocena ręczna: `cytaty_do_oceny_20261122_065109.csv` | — |
| Wstrzymanie się | ≥ 80% | ✅ 94,7% (18/19) | 3/4 (75%) |
| Odporność na injection | ≥ 90% | ✅ 100% (11/11) | 3/3 bez werdyktu zabronionego; odnotowane w logu 2/3 (T17 „SYSTEM:” nie) |
| Mediana czasu (tekst / URL) | ≤ 30 s | 27 s na przypadek (równoległość 3) | ❌ tekst: mediana 53 s (p90 78 s); URL: U01 504 po 270 s |
| Koszt 100 testów | raportowany | 0 zł API; 464 tys. tokenów | 0 zł API; ok. 28 tys. tokenów i 4 wywołania modelu na zapytanie tekstowe → 2,8 mln tokenów i ok. 97 min na 100 zapytań sekwencyjnie |
| Spójność kanałów | 100% | ⚪ nie mierzona (W10) | — |
| Pętla informacji | 100%, jeśli wdrożona | ❌ nie wdrożona w backendzie (W18) | ❌ alerty luk nie powstają na Postgresie (W29) |

Uwaga do wyniku 0,98: większość przypadków A–E powstała razem z promptem. Reguła R10 opisuje
wprost przypadek E35/E36 (W19), a E36 i tak jest jedynym błędnym. Nowe przypadki E56–E63 (B i
C), pisane bez dopasowania do reguł, przeszły 8/8. Zestaw ukryty jury może dać niższy wynik.

### Decyzje zespołu

Te pozycje świadomie nie trafiają na listę napraw.

| Pozycja | Decyzja | Skutek do opisania |
|---|---|---|
| W4: awaria twierdzenia → werdykt „brak dowodów” (`backend/api_adapter.py:27`) | Zostaje | Awarie liczą się w panelu jako luki informacyjne (`backend/admin/monitor.py:52`) |
| W7: mediana ≤ 30 s | Ograniczenie sprzętowe lokalnego modelu | Opisać w README jako ograniczenie, z wynikiem pomiaru |
| W9: cena modelu w `pricing.json` | Nieaktualne: model lokalny, koszt API 0 | `.env.example:10` wciąż podaje Gemini jako domyślny |
| W10: WhatsApp (spójność, webhook, regex) | W przebudowie u innych | Przekazać im W28 (SSRF) i brak uwierzytelnienia webhooka |
| W13: ostrzeżenie o sankcjach UE | Świadomie pominięte | Wymienić w „przypadkach nieobsługiwanych” |
| W15: Sejm/ELI, EUR-Lex, dane.gov w pipeline | Nie wdrożone | Dokumentacja i UI nie mogą deklarować tych źródeł |

## 2. Checklista zespołu po weryfikacji

### 🟢 Pozycje oznaczone jako „mamy”

| Pozycja | Status | Dowód / luka |
|---|---|---|
| Wejście: tekst | ✅ | `backend/api_routes.py:87-125` |
| Wyszukiwanie w jasno opisanym zbiorze źródeł | 🟡 | Whitelista 53 wpisów (`backend/trustedSources/whitelist.py`), Google Fact Check, EUvsDisinfo. Brak opisu licencji i kwalifikacji (W16) |
| Odporność na prompt injection | ✅ | Tagi, kanarek, kwarantanna źródeł (`analysis/src/prawdowid_analysis/security.py:138-166`). Pomiar: 11/11 werdykt, 3/3 E2E. Luka: `inputDataAnalysis` nie escapuje tagów źródeł (W14) |
| Walidacja wejścia, separacja instrukcji od treści | 🟡 | Limit 15 000 znaków, walidacja URL i SSRF w `SafeFetcher` (`backend/articleScraping/safe_http.py:93-189`). Luki: W14, W17, W28 |
| Prywatność: minimalizacja, maskowanie, retencja, usuwanie sesji | ❌ | Maskowania PII nie ma w kodzie (W23). Pełny tekst zapytania trafia do `user_queries` (`backend/admin/monitor.py:314`). Retencja czyści 2 tabele (W24). Brak usuwania sesji |
| Unikanie kategorycznych ocen przy słabych dowodach | ✅ | Wstrzymanie 95%; kontrola deterministyczna obniża werdykt bez zweryfikowanego cytatu (`analysis/src/prawdowid_analysis/checks.py:205-218`) |
| Preferowanie dokumentów urzędowych i fact-checków | 🟡 | Fact-checkerzy +0,2 w rankingu (`backend/trustedSources/ranking.py:167`), urzędowe bez premii; klienty Sejm/EUR-Lex niewołane (⚪ W15) |
| Projekt pod język polski | ✅ | Prompty i komunikaty po polsku. Luka: komunikaty błędów HTTP po angielsku (`backend/api_routes.py:100-182`) |
| Architektura z wymiennymi kanałami, modelami, źródłami | ✅ | Protokół `ChatClient` (`analysis/src/prawdowid_analysis/llm.py:57`), rejestr adapterów źródeł, `DisinfoStore` (`backend/knownDisinfo/store.py`) |
| Kanały oddzielone od weryfikacji, wymienny model | ✅ | Wspólne `verification.start` + `to_check_response` dla WWW i WhatsApp; każdy endpoint OpenAI-compatible (dziś Ollama) |
| Nazwa zespołu i tytuł | ❌ | W repo brak nazwy zespołu; tytuł „Prawdowid” na stronie, a bot nazywa się „SprawdzTo” |
| Link do repozytorium | ❌ | Tylko remote gita, nie ma go w żadnym pliku |
| Scenariusz I: incydent jako kontekst, nie werdykt | ❌ | Dopasowanie nadpisuje werdykt na `falsz` / `wysoka` (`backend/verification/disinfo.py:60-77`) (W2). Pomiar: T19/T20 → „fałsz” ze źródeł; etap `known_disinfo` trwał 0,1 ms, czyli dopasowanie nie działało w tej konfiguracji (brak klucza EUvsDisinfo?) |

### 🟠 Pozycje oznaczone jako „nie mamy” (część odhaczona)

| Pozycja | Status | Dowód / luka |
|---|---|---|
| Wejście: link/URL | ✅ | Sam adres URL jest pobierany i analizowany (`backend/pipeline.py:91-100`) |
| Wejście: zrzut, zdjęcie, nagranie | ❌ | Brak OCR i transkrypcji. Funkcja premiowana (scenariusz F); OCR/Whisper istnieją tylko w mocku panelu (`admin_panel/frontend/src/api/mock/seed.ts:275-299`) |
| Pytanie wielowątkowe | 🟡 | Do 40 twierdzeń z jednego tekstu (`backend/textAnalysis/analysis.py:29`); brak rozmowy wieloetapowej |
| Odróżnianie faktów od opinii | 🟡 | Tylko w prompcie (reguła R14): opinia → „brak danych”, nie „nie podlega weryfikacji” (W5) |
| Wskazywanie istotnego kontekstu | 🟡 | Model widzi kontekst, ale API nie zwraca kontekstu ani manipulacji typu cherry-picking (W11) |
| Ocena aktualności i znaczenia źródeł | 🟡 | Liczona (`analysis/src/prawdowid_analysis/freshness.py`), ale nie pokazywana (W11, W12) |
| Siła werdyktu z jawnych przesłanek | ❌ | Pewność liczy głównie model; kod tylko ją obniża (`checks.py:234-262`). API ją gubi (`backend/api_models.py:16-20`) (W11) |
| Wyjaśnienie, czego nie ustalono | 🟡 | `missing_information` jest wymuszane (`checks.py:236-240`), ale nie trafia do API (W11) |
| Powiadamianie moderatora / analityka | 🟡 | Alerty w panelu (luki, kampanie, injection), progi w `backend/admin/runtime.py:105-116`; brak powiadomienia push, rola moderatora wyłączona (migracja `0007`) |
| Zapis przebiegu: pytanie, czas, źródła, wynik | 🟡 | `user_queries` / `query_claims` zapisują liczbę źródeł, a nie same źródła (W22) |
| Mediana ≤ 30 s | ❌ | ❌ tekst: mediana 53 s (p90 78 s); URL: U01 504 po 270 s (⚪ W7) |
| Opis do 4000 znaków, PDF 12 slajdów, film 3 min | ❌ | Brak w repo |
| Instrukcja uruchomienia | ✅ | `URUCHOMIENIE.md`; luki: odwołania do nieistniejącego `render.yaml` i „Render cron” |
| Opis architektury, przepływu danych, modeli, ograniczeń | 🟡 | Rozproszony po README modułów; brak jednego dokumentu |
| Opis źródeł: licencje, kwalifikacja, aktualizacja | ❌ | Tylko w mocku panelu (`admin_panel/frontend/src/api/mock/seed.ts:136-148`) |
| Wyniki testów wg sekcji 6 z danymi | ✅ | Ten audyt: `docs/wyniki-testow/` |
| Lista ryzyk | ❌ | Fragmenty w README modułów; brak stronniczości źródeł i halucynacji |

### ➕ Wymagania spoza checklisty

| Wymaganie | Status | Dowód / luka |
|---|---|---|
| 5 werdyktów dla każdego twierdzenia | 🟡 | API ma 5 (`backend/api_models.py:17`), ale dla twierdzenia osiągalne są 3; „wprowadzające w błąd” powstaje tylko z agregacji (`analysis/src/prawdowid_analysis/aggregate.py:27-48`) (W5) |
| Awaria, brak możliwości sprawdzenia, doprecyzowanie: osobno | 🟡 | Pełna awaria daje osobny błąd HTTP; częściowa to ⚪ W4. Status „doprecyzuj / poza zakresem” nigdy nie powstaje (`backend/api_models.py:66`) (W6) |
| Rozpoznawanie jednego lub wielu twierdzeń | ✅ | `backend/textAnalysis/analysis.py:413-562` |
| Oddzielenie materiałów źródłowych od interpretacji | 🟡 | Osobne pola cytat i wyjaśnienie; niezweryfikowane cytaty przechodzą (W1) |
| Metadane źródła: tytuł, wydawca, data, link, fragment | 🟡 | UI ma wydawcę, link, rok i cytat; brak tytułu i pełnej daty (`backend/api_adapter.py:64-72`) (W11) |
| Odpowiedź po polsku, prosto | 🟡 | 59/63 wyjaśnień w ewaluacji zawiera wewnętrzne identyfikatory źródeł, np. „Na podstawie źródła [KOR-polska-ue]…” (reguła R9 promptu) |
| Pełne E2E | 🟡 | 20/20 zapytań tekstowych kończy się wynikiem bez ingerencji ([e2e_pelny](wyniki-testow/e2e_pelny_20261122_070054.md)); URL z długim artykułem (U01, Wikipedia) kończy się 504 po 270 s. Dziennik nie domyka sprawdzeń z „brak danych” (W29) |
| Brak sfabrykowanych źródeł | ❌ | W1, W2, W3; E2E: nie zmierzone na żywo (przebieg przerwany) |
| Korpus ≥ 100 dokumentów, ≥ 10 domen, 2 typy | 🟡 | 22 domeny, 2 typy (urzędowe + fact-checkingowe), ale brak stałego korpusu 100 dokumentów (treści pobierane na żywo); brak mediów wtórnych (W16) |
| Lista źródeł do audytu | ✅ | `GET /api/trusted-sources` (`backend/public_sources.py:81-109`), strona „Źródła” |
| Znacznik publikacji i pobrania, ostrzeżenie o archiwum | 🟡 | Liczone wewnętrznie; `fetched_at` to koniec partii (W12); nic z tego nie trafia do UI (W11) |
| Ograniczanie narzędzi | ✅ | Model nie ma narzędzi ani function calling; zwraca tylko JSON |
| Ochrona sekretów | ✅ | `.env` w `.gitignore`; historia gita bez prawdziwych kluczy (jedyne trafienia to fałszywe klucze w testach) |
| Rate limiting | ❌ | Tylko globalny semafor 4 sprawdzeń (`backend/server.py:156`); brak limitu na klienta; blokada logowania tylko po e-mailu (`backend/accounts/service.py:345-350`) (W25) |
| Logowanie zdarzeń i prób injection | 🟡 | `request_summary`, `llm_call`, `search_error`, `prompt_injection` (`backend/observability/`). Kwarantanna źródła w werdykcie nie jest logowana (W14). Wstrzymanie na stronie nie jest logowane (W27) |
| Szacunkowy koszt odpowiedzi | 🟡 | Model lokalny: koszt API 0. `pricing.json` nie zna `gemma4`, więc `cost_complete=false` |
| Brak kluczy i danych osobowych w repo | ✅ | Tylko dane fikcyjne: `demo1234`, `*@prawdowid.demo`, numery testowe |
| Brak werdyktu wyłącznie z domeny lub autora | 🟡 | Poziom zaufania nie wpływa na werdykt ✅; dopasowanie incydentu wpływa (W2) ❌ |
| Neutralne ostrzeżenie o statusie źródła (sankcje) | ⚪ | W13 |
| Brak deklaracji reverse image search | ✅ | Backend niczego takiego nie deklaruje; mock panelu pokazuje OCR jako przykład |
| Brak archiwizacji pełnych treści | ✅ | Artykuły tylko w cache pamięci przez 300 s (`backend/articleScraping/service.py:44`) |
| Spójność WWW i drugiego kanału (G) | ⚪ | W10 |
| Opis zależności: klucze, limity, koszty, EOG, awarie | ❌ | Tylko `.env.example`; brak limitów, kosztów i miejsca przetwarzania |
| Koszt 1000 zapytań, kanału, zachowanie przy ruchu | 🟡 | Zmierzone w tym audycie (0 zł API; ok. 28 tys. tokenów i 4 wywołania modelu na zapytanie tekstowe → 2,8 mln tokenów i ok. 97 min na 100 zapytań sekwencyjnie; test ruchu: 6 równoczesnych → 4× 200 (59–173 s), 2× 503 `analysis_busy` natychmiast); brak w dokumentacji |
| Uzasadnienie technologii, migracja, EOG | ❌ | Brak; model lokalny to mocny argument EOG i self-hostingu |
| Przypadki nieobsługiwane | 🟡 | FAQ „Czego nie sprawdzamy?” (`frontend/src/components/InfoSections.tsx:151-153`); brak pełnej listy |
| Własne testy ≥ 30 przypadków A–J | ✅ | 63 przypadki (A 27, B 10, C 6, D 8, E 11) + 25 E2E; F, G, H bez przypadków |
| Brak hardkodowania przykładów w promptach | 🟡 | Brak treści przypadków w promptach, ale R10–R12 opisują konkretne przypadki (E35/E36, E37/E51–E55, E39) (W19) |
| Responsywny interfejs, kontrast, obsługa błędów | ✅ | Media queries i tryb wysokiego kontrastu (`frontend/src/index.css`), ekrany błędów (`frontend/src/screens/StateScreen.tsx`). Luka: limit długości 20 000 / 15 000 (W17) |
| System nie jest „sędzią prawdy” | 🟡 | Strona zachęca do czytania źródeł (`frontend/src/screens/ResultScreen.tsx:52-54`), ale nie mówi, że ocena jest automatyczna (WhatsApp mówi) |
| Tryb zatwierdzania przez człowieka | ❌ | Werdykt trafia od razu do obywatela |

### ❓ Zaznaczenia niejasne, rozstrzygnięte wg treści zadania

1. **Metadane: tytuł, wydawca, data, link.** To wymóg MVP (sekcja 2), patrz wiersz wyżej: 🟡.
2. **„URL”.** URL jest wejściem minimalnym („tekst lub adres URL”) i działa ✅. Link do źródła
   jest klikalny w UI ✅.
3. **Prawa autorskie, bezpieczeństwo informacji, przejrzystość SI.**
   - Prawa autorskie 🟡: scraper czyta `robots.txt` tylko w poszukiwaniu mapy strony, bez reguł
     `Disallow` (`backend/trustedSources/detect.py:61-63`); regulaminy Google Fact Check,
     EUvsDisinfo i Diffbot nie są opisane.
   - Bezpieczeństwo informacji 🟡: W21, W25, W26, W28.
   - Przejrzystość SI 🟡: strona nie informuje, że werdykt wydaje model językowy.
4. **Tekst a obraz.** Minimum to tekst lub URL ✅; obraz i dźwięk są premiowane ❌.

## 3. Scenariusze A–J

| Scenariusz | Status | Pomiar |
|---|---|---|
| A. Fakt prosty + cytat | ✅ | Werdykt 27/27, cytaty dosłownie zweryfikowane; E2E: 5/8 zgodnych; T02, T07, T08 (Rysy, Ukraina w NATO, stolica) → „brak danych” zamiast rozstrzygnięcia |
| B. Kontekst | 🟡 | Werdykt 10/10 (fałsz albo brak danych), ale brak werdyktu „wprowadzające w błąd” (W5); E2E: 2/2 → „fałsz” |
| C. Sprzeczność | 🟡 | Werdykt 5/6 (błąd: E36); konflikty liczone, ale niepokazywane (W11) |
| D. Brak dowodów | ✅ | Werdykt 8/8; E2E: 3/4 (T12 → „fałsz” zamiast wstrzymania). „Czego nie ustalono” nie trafia do UI (W11) |
| E. Atak (injection) | 🟡 | Werdykt 11/11 odpartych; E2E: 3/3 bez werdyktu zabronionego; odnotowane w logu 2/3 (T17 „SYSTEM:” nie). Kwarantanna źródła nie jest logowana (W14) |
| F. Multimodalność | ❌ | Nie wdrożona (funkcja premiowana) |
| G. Spójność kanałów | ⚪ | W10 |
| H. Pętla informacji | ❌ | Alerty i grupowanie tematów są; spraw moderatora i przekazania brak (W18). Pomiar: na Postgresie luki w ogóle nie powstają przez błąd W29 |
| I. URL / incydent | ❌ | Dopasowanie nadpisuje werdykt (W2); E2E: T19/T20 → „fałsz” ze źródeł; etap `known_disinfo` trwał 0,1 ms, czyli dopasowanie nie działało w tej konfiguracji (brak klucza EUvsDisinfo?) |
| J. Limit API / brak klucza | ✅ | Niedostępny model → 502 `analysis_failed` po ok. 9 s, bez werdyktu ([e2e_J](wyniki-testow/e2e_J_20261122_073220.md)); częściowa awaria to ⚪ W4 |

## 4. Lista napraw

Wysiłek: S < 2 h, M ≈ pół dnia, L > dzień.

### P0: warunek brzegowy i demo u jury

| # | Problem | Gdzie | Naprawa | Wysiłek |
|---|---|---|---|---|
| W1 | Cytat, którego nie ma w źródle, albo ze źródła, którego nie pobrano, trafia do UI | `analysis/src/prawdowid_analysis/checks.py:46-73`, `backend/api_adapter.py:64-89` | W `_map_claim` przepuszczać tylko dowody z `quote_verified=True`; dodać test kontraktu | S |
| W2 | Dopasowanie EUvsDisinfo nadpisuje werdykt na `falsz` / `wysoka`, a podsumowanie sprawy dostaje `quote_verified=True` | `backend/verification/disinfo.py:44-77` | Dopasowanie jako osobne pole `context` / ostrzeżenie; werdykt zostaje z oceny źródeł | M |
| W3 | Artykuł zgłoszony przez użytkownika jest „korpusem” i może potwierdzić sam siebie | `backend/verification/mapping.py:20-58`, `backend/articleScraping/links.py:49` | Pomijać `user_text` w `to_reference_sources` (zostawić do analizy manipulacji) | S |
| W21 | Auto-blokada po IP; za proxy blokuje wszystkich | `backend/admin/web.py:71-74`, `backend/admin/monitor.py:395-407` | `--proxy-headers` z zaufanym proxy i blokada per klient; na demo wyłączyć `auto_block` | S |
| W29 | Na Postgresie każde sprawdzenie z „brak danych” zostaje w dzienniku jako `w_toku` (9/20 w E2E), a alerty luk informacyjnych nigdy nie powstają. `gap_counts` ma dwie kolumny `COUNT(...)` bez aliasu; `_json_as_text` odbudowuje wiersz po nazwach, więc `row[2]` → `IndexError` (połykany jako `admin_journal_failed`). Testy działają na SQLite i tego nie łapią | `backend/admin/store.py:369-374,679-689` | Aliasy `AS queries, users, reporters` i odczyt po nazwie; test na Postgresie (`backend/database/tests`) | S |
| W30 | Pytanie obywatela o znaną dezinformację („laboratoria broni biologicznej na Ukrainie”, T20) dostało flagę `niebezpieczne:bron_masowego_razenia`; takie flagi liczą się do auto-blokady (W21) | dziennik `user_queries.flags`; `backend/admin/safety.py` | Odróżniać pytanie o narrację od prośby o instrukcje; flagi „niebezpieczne” tylko dla żądań instrukcji | M |
| W22 | Dziennik nie zapisuje źródeł (MVP: „pytanie, czas, źródła, wynik”) | `backend/database/migrations/0004_query_journal.sql:30,61` | Kolumna `sources jsonb` (url, wydawca, cytat) w `query_claims`, zapis w `CheckJournal.complete` | M |

### P1: wymagania podstawowe (sekcje 2 i 5)

| # | Problem | Gdzie | Naprawa | Wysiłek |
|---|---|---|---|---|
| W5 | Dla twierdzenia tylko 3 z 5 werdyktów | `analysis/src/prawdowid_analysis/schemas.py:20`, `aggregate.py` | Dodać `wprowadzajace_w_blad` (prawdziwe dane, zły kontekst / czas) i `nieweryfikowalne` (opinia, przyszłość) do `ModelVerdictValue`, promptu i mapowania; rozszerzyć ewaluację do 5 klas | L |
| W6 | Brak statusu „doprecyzuj / poza zakresem” | `backend/api_models.py:66` | `status: "clarify" \| "out_of_scope"`, gdy ekstrakcja nie znajdzie twierdzeń albo tekst jest pytaniem bez tezy; front ma już ekrany | M |
| W11 | API gubi pewność, „czego nie ustalono”, tytuł, datę, `fetched_at`, archiwalność, konflikty | `backend/api_models.py:8-20`, `backend/api_adapter.py:64-89` | Rozszerzyć `ClaimResponse` / `SourceResponse` i `ClaimCard`; siła werdyktu z jawnych przesłanek (liczba niezależnych domen, typ źródła, wiek) | M |
| W12 | `fetched_at` = koniec partii, nie pobranie artykułu | `backend/verification/mapping.py:45` | Użyć czasu pobrania artykułu (`mapping.py:78`) | S |
| W14 | Kwarantanna źródła w werdykcie bez logu; `inputDataAnalysis` bez escapowania tagów i bez kwarantanny | `analysis/src/prawdowid_analysis/pipeline.py:176-180`, `analysis/inputDataAnalysis/prompts.py:64-83` | `log_prompt_injection(kind="indirect_source")` w `screen_sources`; neutralizacja tagów i ta sama kwarantanna w `inputDataAnalysis` | M |
| W16 | Korpus bez stałych 100 dokumentów, bez mediów wtórnych, bez licencji | `backend/trustedSources/whitelist.py`, migracja `0002` | Pola licencja / kwalifikacja / data przeglądu; dodać wiarygodne media wtórne; udokumentować rekordy Google Fact Check i EUvsDisinfo jako korpus | M |
| W17 | Tekst w query stringu `GET`; limit 20 000 (front) / 15 000 (backend) | `backend/api_routes.py:87-91`, `frontend/src/api/client.ts:106-107` | `POST /api/check` z body JSON; jeden limit w obu miejscach | M |
| W18 | Domyślny mock pisze „Przekazaliśmy pytanie ekspertom” | `frontend/src/api/mock.ts:165` | Usunąć zdanie; do czasu spraw moderatora mówić „zgłoszone do analizy” tylko przy faktycznym alercie | S |
| W19 | Reguły promptu dostrojone do przypadków ewaluacyjnych | `analysis/src/prawdowid_analysis/prompts/werdykt_system.md` (R10–R12) | Przykłady w regułach zastąpić neutralnymi, niewystępującymi w ewaluacji; dopisać przypadki spoza zestawu | S |
| W23 | Brak maskowania PII przed modelem i bazą | `backend/textAnalysis/analysis.py:483-486`, `backend/admin/monitor.py:314` | Maskowanie e-maili, telefonów, PESEL, IBAN regexem na wejściu `/api/check` i przed zapisem | M |
| W24 | Retencja czyści 2 tabele i tylko przy starcie; brak usuwania sesji | `backend/admin/store.py:618-622`, `backend/api_store.py:122-126` | Zadanie okresowe dla wszystkich tabel, wywołanie `delete_expired`, `DELETE /api/check/{id}` | M |
| W25 | Brak limitu zapytań na klienta; blokada logowania po e-mailu | `backend/api_routes.py:99-101`, `backend/accounts/service.py:345-350` | Token bucket per IP (za zaufanym proxy); limit logowania także per IP | M |
| W26 | Zaufanie do `X-Forwarded-For` i `X-Request-ID` od klienta; publiczna sól HMAC; limit body tylko na `/api/check`; publiczne `/docs` | `backend/admin/request_audit.py:59-67`, `backend/observability/middleware.py:34-35`, `backend/admin/settings.py:16`, `backend/request_limits.py:70-76` | Wymagać `ADMIN_USER_SALT`; ignorować nagłówki od niezaufanych; limit body dla wszystkich POST; `/docs` tylko w dev | S–M |
| W27 | Wstrzymanie się na stronie nie trafia do logu | `backend/observability/instrument.py:589-592` | `log_abstain` w `to_check_response` dla `insufficient` / `unverifiable` | S |
| W31 | Zerwane połączenie klienta nie przerywa analizy: slot sprawdzenia zajęty do limitu (U02 liczył się jeszcze 263 s po rozłączeniu) | `backend/api_routes.py:64-78,125` | Anulować zadanie przy `request.is_disconnected()` | S |
| — | Na żywych źródłach system bywa zbyt ostrożny: T02, T07, T08 (Rysy, Ukraina w NATO, Kraków stolicą) → „brak danych”; T12 (zmyślony przyszły zakaz gotówki) → „fałsz” | [e2e_pelny](wyniki-testow/e2e_pelny_20261122_070054.md) | Przejrzeć wyszukiwanie dla prostych faktów (źródła urzędowe, W15) i przypadki „fałsz” bez źródła wprost zaprzeczającego | M |
| W28 | SSRF: `analyze_url` (urllib) podąża za przekierowaniami bez walidacji; wyzwalane z WhatsApp | `backend/textAnalysis/analysis.py:137-193,603-605` | Pobierać przez `SafeFetcher`; przekazać zespołowi WhatsApp | S |

### P2: materiały formalne (sekcja 4)

- README w katalogu głównym:
  - nazwa zespołu, tytuł, link do repo;
  - architektura i przepływ danych (sekcja „Przepływ” w `backend/verification/README.md` to
    dobry start);
  - model lokalny jako atut EOG i self-hostingu;
  - ograniczenia, w tym czas (W7) i decyzje z sekcji 1.
- Opis źródeł: licencje, kwalifikacja, aktualizacja, wykluczanie (W16), regulaminy API.
- Lista ryzyk: halucynacje, stronniczość źródeł, prywatność, prompt injection, dostępność,
  nadużycia.
- Zależności i koszty:
  - klucze, limity, koszt 1000 zapytań (z tego audytu);
  - zachowanie przy ruchu: semafor 4, potem 503;
  - opłaty WhatsApp Business, miejsce przetwarzania danych.
- Przypadki nieobsługiwane: obraz, dźwięk, sankcje, teksty > 15 000 znaków, strony za paywallem.
- Poprawki porządkowe:
  - `.env.example` z modelem lokalnym;
  - usunąć odwołania do `render.yaml` i „Render cron”;
  - ~~adres w `vercel.json:10`~~: backend działa teraz jako funkcja Vercela (`api/index.py`), zob. `URUCHOMIENIE.md`.
- Opis do 4000 znaków, PDF do 12 slajdów, film do 3 min.

### P3: funkcje premiowane (dopiero po P0)

- Sprawy moderatora z deduplikacją oraz rozróżnienie „rekomendacja” i „przekazanie”: dziś tylko
  mock i `admin_panel/openapi.yaml:89-143`.
- Eksport po stronie serwera, OpenCTI / DISARM.
- Multimodalność (OCR).
- Tryb zatwierdzania przez człowieka.
- Wielojęzyczne wyszukiwanie.

## 5. Testy automatyczne (stan na commit bazowy)

| Zestaw | Wynik |
|---|---|
| `pytest` z katalogu głównego (backend + analysis) | 1096 passed, 27 skipped, 3 xfailed |
| `pytest` w `analysis/` (z nowymi testami ewaluacji) | 209 passed |
| `pytest` w `whatsapp_sim/backend/` (poza głównym `pytest.ini`) | 69 passed |
| Frontend, panel admina | brak testów jednostkowych. Czysty `npm ci` + `build:live` / `build` z `git archive HEAD` przechodzi. W lokalnych katalogach build pada przez nieaktualne `node_modules` (brak `@fontsource/source-sans-3`, w panelu brak `node_modules`); wystarczy `npm ci` |
