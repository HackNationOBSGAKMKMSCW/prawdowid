# admin — backend panelu administratora

Moduł zapisuje zapytania użytkowników i wykrywa sytuacje, którymi musi zająć się admin.
Przez HTTP API daje dostęp do logów, alertów i konfiguracji serwisu.

## Uruchomienie

W `backend/.env` ustaw `DATABASE_URL` (PostgreSQL, zob. `backend/database/README.md`), potem:

```bash
cd backend
python -m database migrate
python -m database create-user --email admin@example.pl --name "Jan Kowalski" --role admin
uvicorn server:app --port 8000          # API strony razem z panelem (/api/admin)
# dokumentacja: http://localhost:8000/docs
```

Frontend panelu jest w `admin_panel/frontend` (`npm run dev`, proxy na port 8000).

Panel działa w tym samym procesie co API strony (`server.py` → `mount_admin`), więc każde
`/api/check` trafia do dziennika zapytań (kanał `web`), zgłoszenia błędów dopisują się do
tego samego wpisu, a zmiany modeli i stron zaufanych działają od razu
(`backend/API.md`, sekcja *Admin panel*). `ADMIN_PANEL=off` wyłącza panel w `server.py`.
Sam panel, bez potoku weryfikacji: `uvicorn admin.api:create_app --factory --port 8100`
(wtedy w panelu `ADMIN_API_PROXY_TARGET=http://127.0.0.1:8100`).

Logowanie: `POST /api/admin/auth/login` (e-mail i hasło konta z tabeli `users`) zwraca token sesji.
Każde żądanie poza `/health` i `/auth/login` wymaga nagłówka `Authorization: Bearer <token sesji>`.
Role sprawdza backend (`accounts/permissions.py`).

Bez `DATABASE_URL` nie ma kont; panel działa wtedy tylko z awaryjnym `ADMIN_API_TOKEN`
(nieustawiony = wyłączony). Zmienne z `backend/.env` nie nadpisują tych ze środowiska.

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `DATABASE_URL` | brak | PostgreSQL: konta, sesje, dziennik zapytań i działań |
| `ADMIN_API_TOKEN` | brak | Awaryjny dostęp bez konta (najlepiej nie ustawiać) |
| `ADMIN_DB_PATH` | `backend/admin/data/admin.db` | Baza SQLite z zapytaniami, alertami i audytem |
| `RUNTIME_CONFIG_FILE` | `backend/admin/data/runtime_config.json` | Nadpisania konfiguracji |
| `ADMIN_IP_SALT` | losowa, w bazie | Sól HMAC adresów IP w blokadach po prompt injection |
| `CLIENT_IP_HEADER` | `cf-connecting-ip` | Nagłówek zaufanego proxy z adresem klienta (pusty = nie ufaj) |
| `TRUSTED_PROXY_HOPS` | `1` | Ile zaufanych proxy dopisuje się do `X-Forwarded-For` (0 = adres połączenia) |

Katalog `data/` jest w `.gitignore`, bo może zawierać klucze API.

## Integracja z potokiem

```python
from admin import ClaimInput, get_monitor

monitor = get_monitor()
decision = monitor.screen(text=text, channel="whatsapp")  # bez numeru nadawcy
if not decision.allowed:
    return decision.message  # treść wysokiego ryzyka
analysis = await textAnalysis.run(text)
...
result = monitor.complete(
    decision.query_id,
    claims=[ClaimInput(claim.statement, claim.verdict, len(claim.sources)) for claim in ...],
    verdict=text_verdict,
)
if result.message:  # stan luki informacyjnej: dołącz do odpowiedzi
    reply += "\n\n" + result.message
```

`monitor.record(...)` robi oba kroki naraz, gdy potok już się wykonał.

API strony (`admin/web.py`, `CheckJournal`) i bot WhatsApp
(`whatsapp_sim/backend/whatsappAdapter/admin_bridge.py`) są już wpięte.
Rejestruje każdą wiadomość do sprawdzenia (bez danych o nadawcy), odrzuca treści wysokiego ryzyka,
a do odpowiedzi dołącza komunikat o luce informacyjnej. Bot i panel muszą mieć to samo
`ADMIN_DB_PATH`. `ADMIN_MONITOR=off` wyłącza rejestr. Awaria monitora nie przerywa rozmowy.

## Reguły

Progi ustawia się w sekcji `monitoring` konfiguracji (`PATCH /api/admin/config`, w panelu
„Reguły i progi”). Działają od następnego zapytania.

**Bez danych o użytkownikach aplikacji.** Dziennik nie zapisuje numeru telefonu, adresu IP,
pseudonimu ani żadnego innego identyfikatora osoby pytającej (`user_key` = `anonim`,
`user_label` = `NULL`). Dlatego wszystkie reguły liczą **zapytania**, a nie osoby, a alert o
treściach niebezpiecznych jest zbiorczy. Migracja `0010_no_end_user_data` usuwa dane zapisane
wcześniej (tabela `end_users`, pseudonimy, źródła w alertach). Jedyny wyjątek to adres, z
którego przyszła próba prompt injection: trafia do `ip_blocks` (migracja `0011`) jako klucz
HMAC z maską, żeby można go było zablokować.

- **Luka informacyjna.** Twierdzenie jest jej kandydatem, gdy nie ma rozstrzygnięcia: werdykt `brak_wystarczajacych_danych` albo `nieweryfikowalny`, albo brak jakichkolwiek źródeł.
  - Podobne twierdzenia są grupowane w tematy.
  - Próg: `info_gap_min_queries` zapytań bez pokrycia (domyślnie 3) w oknie `info_gap_window_hours` (domyślnie 7 dni). Dwa twierdzenia z jednego zapytania liczą się raz. Pola `info_gap_count_by` i `info_gap_min_users` zostały tylko dla zgodności i są nieużywane.
  - Po przekroczeniu progu temat dostaje stan `aktywna`, powstaje alert, a osoba pytająca dostaje komunikat o luce.
  - W tematach jest licznik `gap_queries` (`gap_users` zawsze 0).
  - Stany: `podejrzenie` → `aktywna` → `w_uzupelnianiu` → `zamknieta` albo `odrzucona`.
  - Pierwsze rozstrzygnięcie oparte na źródłach (prawda/fałsz) zamyka lukę automatycznie.
- **Możliwy atak dezinformacyjny.** Alert `kampania_dezinformacyjna` powstaje, gdy `disinfo_min_users` **zapytań** (nazwa pola historyczna; domyślnie 5 w ciągu 24 h) dotyczy tematu ocenionego jako fałsz. Przy co najmniej dwukrotności progu alert ma ważność `wysoka`.
- **Treści niebezpieczne:** terroryzm, materiały wybuchowe, broń, broń masowego rażenia, przemoc masowa.
  - Pytanie o fakt, np. „czy zamach w X był…”, dostaje poziom `sredni`: jest przetwarzane i oznaczane.
  - Prośba o instrukcję, przepis lub zdobycie dostaje poziom `wysoki` i jest odrzucana.
  - `dangerous_alert_after` zapytań (łącznie) w oknie `dangerous_window_hours` daje zbiorczy alert `tresci_niebezpieczne` (temat `wszystkie`, w szczegółach kategorie i liczba próśb wysokiego ryzyka).
  - Nikt nie jest blokowany (`refuse_high_risk` odrzuca same prośby wysokiego ryzyka).
- **Prompt injection.** Każda próba dostaje flagę `prompt_injection` i trafia jako wystąpienie do alertu `prompt_injection`: jeden alert na adres IP strony (`ip:<klucz>`), a bez adresu (WhatsApp) na kanał. Od `injection_block_after` prób z jednego adresu (domyślnie 1) w oknie `dangerous_window_hours` adres jest blokowany na `injection_block_hours` (domyślnie 24 h, `injection_block_ip`): to zapytanie i kolejne dostają `403 user_blocked`. Admin blokuje i odblokuje w panelu (alert albo „Zagrożenia”). Szczegóły: [ALERTS_FRONTEND.md](ALERTS_FRONTEND.md).
- **Zweryfikowana rosyjska dezinformacja.** Twierdzenie z zapytania na stronie jest w bazie EUvsDisinfo (`knownDisinfo`, MCP). Powstaje wtedy alert `rosyjska_dezinformacja`, jeden na przypadek z bazy. Każde kolejne zapytanie zwiększa licznik i dopisuje się do `details.wystapienia`, a zapytanie dostaje flagę `rosyjska_dezinformacja`.
- **SQL injection.** `admin/sqli.py` szuka składni SQL (UNION SELECT, `' OR '1'='1`, `; DROP TABLE`, SLEEP itp.):
  - w każdym żądaniu API strony i panelu (`admin/request_audit.py`, middleware w `server.py` i `admin/api.py`);
  - w wiadomościach bota.

  Powstaje alert `sql_injection`, jeden na kanał, z licznikiem prób. Nic nie jest blokowane. W alercie nie ma wartości pól.

  Skan i zapis alertu robi w tle wątek roboczy (`admin/background.py`, ograniczona kolejka), więc żądanie nie czeka. Ten sam wątek zapisuje sprawdzenia ze strony do rejestru luk.
- **Retencja.** Zapytania starsze niż `retention_days` (domyślnie 30) są usuwane przy starcie panelu albo przez `POST /maintenance/purge`.

## Zmiana modeli i kluczowych API

`PATCH /api/admin/config` zapisuje nadpisania w pliku JSON. Wartość `null` przywraca to, co jest w `.env`.

`Settings.from_environment()` (textAnalysis, werdykt) i `inputDataAnalysis.config.get_settings()` nakładają nadpisania na `os.environ` przy każdym zapytaniu. Zmiana działa więc bez restartu we wszystkich etapach, także w procesie bota.

| Pole | Zmienna środowiskowa |
|---|---|
| `llm.model` | `FREELLM_MODEL`: analiza wejścia, textAnalysis i werdykt |
| `llm.text_analysis_model` | `TEXT_ANALYSIS_MODEL`: tylko textAnalysis |
| `llm.base_url`, `llm.timeout_s`, `llm.max_retries` | `FREELLM_BASE_URL`, `FREELLM_TIMEOUT`, `FREELLM_MAX_RETRIES` |
| `apis.disabled_clients` | `API_READING_DISABLED_CLIENTS`: np. `["sejm", "eurlex"]` |
| `apis.article_scraping_enabled`, `apis.article_extractor` | `ARTICLE_SCRAPING_ENABLED`, `ARTICLE_EXTRACTOR` (`local`/`diffbot`) |
| `secrets.*` | `FREELLM_API_KEY`, `GOOGLE_FACT_CHECK_API_KEY`, `DIFFBOT_API_TOKEN` |

Klucze są tylko do zapisu. API i audyt pokazują wyłącznie maskę (`****abcd`).

`GET /config/models` pobiera listę modeli z endpointu dostawcy.

## Endpointy (`/api/admin`)

| Metoda i ścieżka | Opis |
|---|---|
| `GET /dashboard` | Liczniki, werdykty, otwarte alerty, aktywne luki, treści niebezpieczne |
| `GET /queries` | Logi zapytań (bez danych o osobach). Filtry: `flag`, `verdict`, `status`, `since`, `until`, `q` |
| `GET /queries/{id}` | Szczegóły zapytania z twierdzeniami i zgłoszeniem błędu (`report`) |
| `GET /events`, `GET /events/summary` | Techniczne logi observability (`backend/logs/app.jsonl`) |
| `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}` | Alerty i zmiana ich statusu |
| `GET /ip-blocks`, `POST /ip-blocks/{ip_key}/block`, `POST /ip-blocks/{ip_key}/unblock` | Adresy po prompt injection (maska), blokada i odblokowanie |
| `GET /info-gaps`, `POST /info-gaps/{topic_id}`, `GET /topics/{id}` | Luki informacyjne |
| `GET /info-gaps/summary` | Ile zapytań w oknie nie miało pokrycia w danych, liczba tematów w każdym stanie, najczęstsze tematy |
| `GET /info-gaps/ranking` | Tematy z największą liczbą zapytań bez pokrycia (także poniżej progu), z trendem dziennym |
| `GET /config`, `PATCH /config` | Konfiguracja modeli, API i progów |
| `GET /config/audit`, `GET /config/models` | Historia zmian konfiguracji i dostępne modele |
| `POST /maintenance/purge` | Ręczne usunięcie starych danych |
| `GET`/`POST`/`PATCH`/`DELETE /sources` (`?url=`) | Strony zaufane w bazie (`trusted_sources`) |
| `GET /sources/status` | Te same strony w rejestrze weryfikacji: wykryty sposób wyszukiwania, ostatnie sprawdzenie |
| `POST /sources/check?url=` | Ponowne wykrycie, jak przeszukiwać stronę (pobiera ją) |
| `GET /health` | Bez logowania: stan panelu i bazy (`store`, `database`) |

Flaga `zgloszenie:<powód>` w `GET /queries?flag=zgloszenie` to wyniki, w których ktoś zgłosił
błąd na stronie (`wrong_verdict`, `bad_source`, `misunderstood`, `other`).

Panel nie ma widoku użytkowników aplikacji. `GET /accounts` i pozostałe endpointy kont obsługują
wyłącznie konta panelu (role `analyst` i `admin`); konta z rolą `user` są dla panelu niewidoczne.

Nowe typy alertów (rosyjska dezinformacja, SQL injection) dla frontu: [ALERTS_FRONTEND.md](ALERTS_FRONTEND.md).

Opis endpointów luk informacyjnych dla frontu (parametry, przykładowe odpowiedzi, sugerowany widok): [INFO_GAPS_FRONTEND.md](INFO_GAPS_FRONTEND.md).
