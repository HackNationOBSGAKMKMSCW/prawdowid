# database: PostgreSQL serwisu

Jedna baza przechowuje:
- konta i hasła (hashowane),
- tokeny dostępu i typy kont,
- listę stron zaufanych,
- dziennik działań w aplikacji,
- dziennik zapytań użytkowników.

Kod:
- `database/` odpowiada za połączenie, migracje i CLI;
- `accounts/` obsługuje konta, logowanie, tokeny, strony zaufane, dziennik działań i API;
- `admin/store.py` zawiera `PostgresAdminStore`, czyli dziennik zapytań i alerty.

## Uruchomienie

1. W `backend/.env` ustaw adres bazy (wzór w `.env.example`):

   ```
   DATABASE_URL=postgresql://uzytkownik:haslo@host:5432/prawdowid
   ```

2. Z katalogu `backend/` uruchom:

   ```bash
   python -m database check          # połączenie, istniejące tabele, stan migracji (nic nie zmienia)
   python -m database migrate        # tworzy brakujące tabele
   python -m database seed-sources   # wgrywa listę stron z trustedSources/whitelist.py
   python -m database create-user --email admin@example.pl --name "Jan Kowalski" --role admin
   ```

   Hasło nowego konta podajesz w terminalu (bez echa) albo w zmiennej `NEW_USER_PASSWORD`.

Migracje to pliki `migrations/NNNN_nazwa.sql`. Każda jest stosowana raz i zapisywana w `schema_migrations` razem z sumą kontrolną. Zmiana bazy to nowy plik: edycja zastosowanej migracji jest błędem.

## Schemat (DBML, do wklejenia w dbdiagram.io)

```dbml
Enum user_role { user  moderator  analyst  admin }

Table users {
  id integer [pk, increment]
  name varchar(100) [not null]
  email varchar(255) [not null, note: 'unikalny bez względu na wielkość liter']
  password_hash varchar(255) [not null, note: 'scrypt$n$r$p$sól$hash']
  role user_role [not null, default: 'user']
  is_active boolean [not null, default: true]
  last_login_at timestamptz
  created_at timestamptz [not null]
  updated_at timestamptz [not null]
}

Table auth_access_tokens {
  id integer [pk, increment]
  tokenable_id integer [not null, ref: > users.id, note: 'ON DELETE CASCADE']
  type varchar(255) [not null, note: 'auth_token']
  name varchar(255)
  hash varchar(255) [not null, unique, note: 'SHA-256 sekretu; sam token nie jest zapisywany']
  abilities text [not null, note: 'JSON, np. ["*"] albo ["alerts:read"]']
  created_at timestamptz
  updated_at timestamptz
  last_used_at timestamptz
  expires_at timestamptz
}

Table trusted_sources {
  url text [pk]
  name text [not null]
  topics "text[]" [not null]
  description text [not null]
  adapter text [note: 'NULL = rozpoznaj automatycznie']
  params jsonb [not null]
  enabled boolean [not null, default: true]
  created_at timestamptz
  updated_at timestamptz
  updated_by integer [ref: > users.id]
}

Table activity_logs {
  id bigint [pk, increment]
  occurred_at timestamptz [not null]
  user_id integer [ref: > users.id, note: 'ON DELETE SET NULL']
  actor varchar(255) [not null, note: 'email/nazwa w chwili działania']
  action varchar(100) [not null, note: 'auth.login, user.updated, source.created, config.updated…']
  subject_type varchar(50)
  subject_id varchar(255)
  details jsonb [not null]
  ip_address inet
  user_agent varchar(255)
}

Table user_queries {
  id varchar(32) [pk]
  ts timestamptz [not null]
  user_key varchar(64) [not null, ref: > end_users.user_key, note: 'pseudonim (HMAC)']
  user_label varchar(32)
  account_id integer [ref: > users.id, note: 'gdy pyta zalogowane konto']
  channel varchar(32)
  text text
  status varchar(32) [not null]
  verdict varchar(64)
  flags jsonb
  safety jsonb
  request_id varchar(64)
  sources_count integer
  completed_at timestamptz
  error text
}

Table end_users {
  user_key varchar(64) [pk]
  label varchar(32)
  first_seen timestamptz
  last_seen timestamptz
  queries integer
  dangerous integer
  blocked_until timestamptz
  block_reason text
}

Table query_topics {
  id varchar(32) [pk]
  label text
  tokens jsonb
  gap_status varchar(32) [note: 'luka informacyjna: brak/podejrzenie/aktywna/…']
  gap_users integer
}

Table query_claims {
  id bigint [pk, increment]
  query_id varchar(32) [ref: > user_queries.id]
  topic_id varchar(32) [ref: > query_topics.id]
  text text
  verdict varchar(64)
  kind varchar(16) [note: 'prawda/falsz/luka/inne']
}

Table monitor_alerts {
  id varchar(32) [pk]
  type varchar(64) [note: 'luka_informacyjna, kampania_dezinformacyjna, niebezpieczny_uzytkownik']
  subject varchar(64)
  severity varchar(16)
  status varchar(32)
  details jsonb
}

Table config_audit {
  id bigint [pk, increment]
  ts timestamptz
  actor varchar(255)
  field varchar(100)
  old jsonb
  new jsonb
}
```

Różnice względem schematu z założeń:
- **Unikalność emaila.** `users.email` jest unikalny bez względu na wielkość liter, przez indeks na `lower(email)`.
- **Dodatkowe pola w `users`.** `is_active` i `last_login_at` są potrzebne panelowi (wyłączanie kont i „ostatnie logowanie”).
- **Role w `user_role`.** Oprócz `user` i `admin` są role panelu `moderator` i `analyst`, zgodne z `admin_panel/frontend/src/auth/permissions.ts`.

## Bezpieczeństwo

- **Hasła.** Hash scrypt z solą, sprawdzany w stałym czasie, także dla nieistniejącego konta. Minimum to 10 znaków i hasło nie może być równe adresowi email.
- **Tokeny.** Format to `oat_<id>.<sekret>`, a w bazie zapisywany jest tylko SHA-256 sekretu.
  - Domyślna ważność to 8 h; token do integracji może działać do 90 dni.
  - Zmiana hasła, zmiana roli i wyłączenie konta unieważniają wszystkie tokeny.
- **Limit logowania.** Po 5 błędnych próbach w ciągu 15 minut dla jednego emaila logowanie odpowiada 429. Próby są zapisywane w `activity_logs` z powodem.
- **Ochrona administratorów.** Nie da się odebrać uprawnień ani usunąć ostatniego aktywnego administratora.
- **Uprawnienia.** Rola i zakres tokenu (`abilities`) są sprawdzane przy każdym żądaniu, a token nie może mieć więcej uprawnień niż rola.
- **Token awaryjny.** `ADMIN_API_TOKEN` działa nadal jako dostęp administratora, np. przed utworzeniem pierwszego konta.

## API

### Panel admina (`uvicorn admin.api:create_app --factory`)

Z ustawionym `DATABASE_URL` panel ma dodatkowo:

| Metoda i ścieżka | Uprawnienie | Opis |
|---|---|---|
| `POST /api/admin/auth/login` | — | `{email, password}` → `{token, user, expiresAt}` (tylko role panelu) |
| `POST /api/admin/auth/logout` | zalogowany | unieważnia bieżący token |
| `GET /api/admin/auth/me` | zalogowany | konto i lista uprawnień |
| `POST /api/admin/auth/me/password` | zalogowany | `{current, new}` |
| `GET/POST/DELETE /api/admin/auth/me/tokens` | zalogowany | tokeny do integracji |
| `GET/POST /api/admin/accounts` | `users:read` / `users:write` | konta panelu i serwisu |
| `PATCH/DELETE /api/admin/accounts/{id}` | `users:write` | rola, nazwa, aktywność |
| `POST /api/admin/accounts/{id}/password` | `users:write` | reset hasła |
| `GET /api/admin/sources` | `sources:read` | lista stron zaufanych |
| `POST /api/admin/sources`, `PATCH`/`DELETE /api/admin/sources?url=…` | `sources:write` | edycja listy |
| `POST /api/admin/sources/seed` | `sources:write` | wgranie listy z kodu |
| `GET /api/admin/activity` | `audit:read` | dziennik działań, filtry: `action` (np. `auth.`), `user_id`, `since` |

Dotychczasowe trasy panelu (`/dashboard`, `/queries`, `/alerts`, `/config`…) wymagają teraz uprawnienia roli, np. `/config` PATCH wymaga `settings:write`. Zmiany zapisują się w `activity_logs`.

### Serwis (`accounts.api.create_service_router(db)`)

Router `/api/auth` dla zwykłych użytkowników:
- `POST /register` (wyłączysz go przez `ACCOUNTS_REGISTRATION=closed`), `POST /login`, `POST /logout`, `GET /me`;
- `GET /me/queries` zwraca historię własnych zapytań z dziennika: wpisy z `account_id`, zapisane przez `monitor.screen(..., account_id=…)`.

## Testy

Testy jednostkowe działają bez bazy. Testy PostgreSQL uruchamiają się z `TEST_DATABASE_URL`, każdorazowo w tymczasowym schemacie `test_<losowy>` usuwanym po testach:

```bash
TEST_DATABASE_URL=postgresql://… python -m pytest backend/database backend/accounts
```
