# admin — backend panelu administratora

Moduł zapisuje zapytania użytkowników i wykrywa sytuacje, którymi musi zająć się admin.
Przez HTTP API daje dostęp do logów, alertów i konfiguracji serwisu.

## Uruchomienie

W `backend/.env` ustaw `DATABASE_URL` (PostgreSQL, zob. `backend/database/README.md`), potem:

```bash
cd backend
python -m database migrate
python -m database create-user --email admin@example.pl --name "Jan Kowalski" --role admin
uvicorn admin.api:create_app --factory --port 8100
# dokumentacja: http://localhost:8100/api/admin/docs
```

Frontend panelu jest w `admin_panel/frontend` (`npm run dev`, proxy na port 8100).

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
| `ADMIN_USER_SALT` | stała | Sól HMAC do pseudonimizacji identyfikatorów użytkowników |
| `RUNTIME_CONFIG_FILE` | `backend/admin/data/runtime_config.json` | Nadpisania konfiguracji |

Katalog `data/` jest w `.gitignore`, bo może zawierać klucze API.

## Integracja z potokiem

```python
from admin import ClaimInput, get_monitor

monitor = get_monitor()
decision = monitor.screen(user_id=sender, text=text, channel="whatsapp")
if not decision.allowed:
    return decision.message  # użytkownik zablokowany albo treść wysokiego ryzyka
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

Bot WhatsApp (`whatsapp_sim/backend/whatsappAdapter/admin_bridge.py`) jest już wpięty.
Rejestruje każdą wiadomość do sprawdzenia, odrzuca zablokowanych i treści wysokiego ryzyka,
a do odpowiedzi dołącza komunikat o luce informacyjnej. Bot i panel muszą mieć to samo
`ADMIN_DB_PATH`. `ADMIN_MONITOR=off` wyłącza rejestr. Awaria monitora nie przerywa rozmowy.

## Reguły

Progi ustawia się w sekcji `monitoring` konfiguracji (`PATCH /api/admin/config`).

- **Luka informacyjna.** Twierdzenie jest jej kandydatem, gdy nie ma rozstrzygnięcia: werdykt `brak_wystarczajacych_danych` albo `nieweryfikowalny`, albo brak jakichkolwiek źródeł.
  - Podobne twierdzenia są grupowane w tematy.
  - Gdy o ten sam temat zapyta `info_gap_min_users` różnych osób (domyślnie 3 w ciągu 7 dni), temat dostaje stan `aktywna`, powstaje alert, a użytkownik dostaje komunikat o luce.
  - Stany: `podejrzenie` → `aktywna` → `w_uzupelnianiu` → `zamknieta` albo `odrzucona`.
  - Pierwsze rozstrzygnięcie oparte na źródłach (prawda/fałsz) zamyka lukę automatycznie.
- **Możliwy atak dezinformacyjny.** Alert `kampania_dezinformacyjna` powstaje, gdy `disinfo_min_users` różnych osób (domyślnie 5 w ciągu 24 h) pyta o temat oceniony jako fałsz. Przy co najmniej dwukrotności progu alert ma ważność `wysoka`.
- **Treści niebezpieczne:** terroryzm, materiały wybuchowe, broń, broń masowego rażenia, przemoc masowa.
  - Pytanie o fakt, np. „czy zamach w X był…”, dostaje poziom `sredni`: jest przetwarzane i oznaczane.
  - Prośba o instrukcję, przepis lub zdobycie dostaje poziom `wysoki` i jest odrzucana.
  - `dangerous_alert_after` zapytań w oknie czasu daje alert `niebezpieczny_uzytkownik`.
  - `dangerous_block_after` zapytań wysokiego ryzyka daje czasową blokadę (`dangerous_block_hours`).
- **Retencja.** Zapytania starsze niż `retention_days` (domyślnie 30) są usuwane przy starcie panelu albo przez `POST /maintenance/purge`.

## Zmiana modeli i kluczowych API

`PATCH /api/admin/config` zapisuje nadpisania w pliku JSON. Wartość `null` przywraca to, co jest w `.env`.

`Settings.from_environment()` nakłada nadpisania na `os.environ` przy każdym zapytaniu. Zmiana działa więc bez restartu, także w procesie bota.

| Pole | Zmienna środowiskowa |
|---|---|
| `llm.model` | `FREELLM_MODEL`: textAnalysis i werdykt |
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
| `GET /dashboard` | Liczniki, werdykty, otwarte alerty, aktywne luki, zablokowani |
| `GET /queries` | Logi zapytań użytkowników. Filtry: `user`, `flag`, `verdict`, `status`, `since`, `until`, `q` |
| `GET /queries/{id}` | Szczegóły zapytania z twierdzeniami |
| `GET /events`, `GET /events/summary` | Techniczne logi observability (`backend/logs/app.jsonl`) |
| `GET /users`, `GET /users/{key}` | Użytkownicy (pseudonimy) i ich historia |
| `POST /users/{key}/block`, `POST /users/{key}/unblock` | Blokada i odblokowanie (`hours: null` blokuje bezterminowo) |
| `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}` | Alerty i zmiana ich statusu |
| `GET /info-gaps`, `POST /info-gaps/{topic_id}`, `GET /topics/{id}` | Luki informacyjne |
| `GET /config`, `PATCH /config` | Konfiguracja modeli, API i progów |
| `GET /config/audit`, `GET /config/models` | Historia zmian konfiguracji i dostępne modele |
| `POST /maintenance/purge` | Ręczne usunięcie starych danych |

Identyfikatory użytkowników są pseudonimizowane (HMAC). Panel pokazuje tylko maskę, np. `***456`.
