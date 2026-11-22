# Uruchomienie Prawdowida: strona, WhatsApp i panel admina

Jeden backend (`server:app`, port 8000) obsługuje wszystko:

| Część | Adres w dev | Skąd |
|---|---|---|
| Backend: API strony, symulatora WhatsApp i panelu admina | http://127.0.0.1:8000 | `backend/server.py` |
| Strona i symulator WhatsApp (`/whatsapp`) | http://localhost:5173 | `frontend/` |
| Panel admina | http://localhost:5175 | `admin_panel/frontend/` |

## Wymagania

- Python 3.14 (`.python-version`; 3.13 też działa),
- Node.js 22 LTS (albo 20.19+; Vite 8),
- PostgreSQL (lokalny albo zdalny).

## Krok 1. Zależności

Z katalogu głównego repozytorium:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd frontend && npm install && cd ..
cd admin_panel/frontend && npm install && cd ../..
```

Windows (PowerShell): zamiast `.venv/bin/python` używaj `.venv\Scripts\python`.

## Krok 2. Plik `.env`

Skopiuj wzór i uzupełnij:

```bash
cp .env.example .env
```

| Zmienna | Co wpisać |
|---|---|
| `DATABASE_URL` | `postgresql://uzytkownik:haslo@localhost:5432/prawdowid` |
| `DATABASE_SSL_MODE` | `disable` dla lokalnej bazy bez SSL |
| `FREELLM_API_KEY`, `FREELLM_BASE_URL`, `FREELLM_MODEL` | model językowy (bez nich sprawdzanie kończy się błędem 502) |
| `GOOGLE_FACT_CHECK_API_KEY` | klucz Google Fact Check Tools |
| `VITE_API_MODE` | `live` – strona łączy się z backendem. **`mock` (domyślne) nie wysyła żadnych zapytań do backendu** |
| `LOG_CONSOLE` | `true` – na konsoli backendu widać każdy etap sprawdzania |

Pozostałe zmienne mają rozsądne wartości domyślne (opisy w `.env.example`).

## Krok 3. Baza danych (tylko za pierwszym razem)

```bash
cd backend
../.venv/bin/python -m database migrate
../.venv/bin/python -m database seed-sources
../.venv/bin/python -m database create-user --email admin@example.pl --name "Jan Kowalski" --role admin
cd ..
```

- `migrate` tworzy tabele,
- `seed-sources` wgrywa startową listę stron zaufanych (bez tego lista źródeł na stronie jest pusta),
- `create-user` pyta o hasło; role: `admin` (pełna kontrola) i `analyst` (tylko podgląd).

Sprawdzenie: `../.venv/bin/python -m database check` (z katalogu `backend/`).

## Krok 4. Backend (terminal 1)

```bash
PYTHONPATH=backend:analysis:analysis/src .venv/bin/uvicorn server:app --port 8000
```

Windows (PowerShell):

```powershell
$env:PYTHONPATH="backend;analysis;analysis/src"; .venv\Scripts\uvicorn server:app --port 8000
```

Działa, gdy http://127.0.0.1:8000/api/health zwraca `{"status":"ok"}`. Logi są na konsoli
i w `backend/logs/app.jsonl`.

## Krok 5. Strona i WhatsApp (terminal 2)

```bash
cd frontend
npm run dev:live
```

- strona: http://localhost:5173,
- symulator WhatsApp: http://localhost:5173/whatsapp (`/clear` czyści rozmowę).

Używaj `dev:live`. Samo `npm run dev` uruchamia tryb demo (czarny pasek „DEMO” na górze):
wyniki są przykładowe, a do backendu nie idzie żadne zapytanie.

## Krok 6. Panel admina (terminal 3)

```bash
cd admin_panel/frontend
npm run dev
```

Otwórz http://localhost:5175 i zaloguj się kontem z kroku 3. Panel przekazuje `/api` do
backendu na porcie 8000 (`ADMIN_API_PROXY_TARGET` w `admin_panel/frontend/.env`, jeśli inny).

Bez bazy, na danych przykładowych: `npm run dev:demo` (konta `admin@sprawdz.to.demo`
i `analityk@sprawdz.to.demo`, hasło `demo1234`).

## Gdy coś nie działa

| Objaw | Przyczyna |
|---|---|
| Wyniki są, ale backend nic nie loguje | strona w trybie demo: użyj `npm run dev:live` albo `VITE_API_MODE=live` |
| 502 przy sprawdzaniu | brak lub zły klucz modelu (`FREELLM_*`); przyczyna jest w logu backendu |
| Lista źródeł pusta | nie wykonano `python -m database seed-sources` |
| Nie da się zalogować do panelu | brak `DATABASE_URL` albo konta (`create-user`) |
| WhatsApp: „Brak odpowiedzi od backendu” | backend nie działa na porcie 8000 |

## Wdrożenie na Vercel (Postgres z Vercela + API OpenAI)

Wszystko działa w jednym projekcie Vercela z katalogu głównego repo (`vercel.json`):

| Część | Gdzie na Vercelu | Adres |
|---|---|---|
| Strona | statyczny build `frontend/` (`npm run build:live`) | `/` |
| Panel admina | statyczny build `admin_panel/frontend/` | `/admin` |
| Backend (FastAPI) | funkcja `api/index.py`, region `fra1`, limit 300 s | `/api/*` |
| PostgreSQL | Vercel Marketplace → Neon (region Frankfurt) | `DATABASE_URL` |
| Model | API OpenAI | `FREELLM_*` |

Strona i panel wołają `/api` w tej samej domenie, więc `VITE_API_BASE_URL` i `CORS_ORIGINS` nie
są potrzebne. Nic nie zależy od Tailscale ani od waszych komputerów.

### Krok 1. Projekt i baza

1. Vercel → Add New → Project → wybierz repozytorium (Root Directory: katalog główny; resztę
   bierze z `vercel.json`).
2. W projekcie: Storage → Create Database → **Neon** (Postgres), region **Frankfurt
   (eu-central-1)**, i podłącz ją do projektu. Vercel sam doda `DATABASE_URL` (adres poolera)
   i `DATABASE_URL_UNPOOLED` do zmiennych.

Region bazy i funkcji (`fra1`) musi być ten sam: backend wysyła do bazy wiele krótkich zapytań.

### Krok 2. Zmienne (Settings → Environment Variables)

| Zmienna | Wartość |
|---|---|
| `FREELLM_API_KEY` | klucz z https://platform.openai.com/api-keys |
| `FREELLM_BASE_URL` | `https://api.openai.com/v1` |
| `FREELLM_MODEL` | `gpt-6.2-sol` |
| `LLM_REASONING_EFFORT` | `low`: najniższy poziom, jaki przyjmuje gpt-6.2-sol (`none` odrzuca) |
| `FREELLM_TIMEOUT` | `60`: limit jednego wywołania modelu w sekundach (bez tej zmiennej część kodu czeka tylko 30 s) |
| `GOOGLE_FACT_CHECK_API_KEY` | klucz Google Fact Check Tools |
| `EUVSDISINFO_API_KEY` | klucz EUvsDisinfo (bez niego to sprawdzenie jest wyłączone) |
| `ADMIN_USER_SALT` | losowy ciąg, np. `openssl rand -hex 32` |

`DATABASE_URL` ustawia integracja z Neonem; `DATABASE_SSL_MODE` zostaw puste (domyślna
weryfikacja certyfikatu działa z Neonem). Opcjonalnie: `LLM_REASONING_EFFORT` (opis w
`.env.example`) i strojenie (`ARTICLE_*`, `TRUSTED_*`, `MAX_CONCURRENT_CHECKS`).

Model można podmienić samą zmienną `FREELLM_MODEL` (i redeployem). Parametry, których dany
model nie przyjmuje, backend dopasowuje sam po pierwszym błędzie 400
(`backend/llm_compat.py`): przy odrzuconym `reasoning_effort: none` próbuje `minimal`, potem
`low`, a odrzucone `temperature` pomija. Każda nowa instancja funkcji uczy się tego od nowa
(dodatkowe nieudane wywołania), dlatego `LLM_REASONING_EFFORT` warto ustawić od razu.
Wywołania narzędzi (tools) nie są używane, więc wystarcza Chat Completions.

### Krok 3. Tabele i konto admina (raz, z własnego komputera)

```bash
npm i -g vercel && vercel link && vercel env pull .env.vercel
export DATABASE_URL="$(grep '^DATABASE_URL_UNPOOLED=' .env.vercel | cut -d= -f2- | tr -d '"')"
cd backend
../.venv/bin/python -m database migrate
../.venv/bin/python -m database seed-sources
../.venv/bin/python -m database create-user --email ... --name "..." --role admin
cd .. && rm .env.vercel
```

Migracje idą przez adres bez poolera (`DATABASE_URL_UNPOOLED`), aplikacja przez pooler.

### Krok 4. Przeniesienie danych ze starej bazy (opcjonalnie)

Zamiast kroku 3, z komputera, który widzi starą bazę (np. w Tailscale):

```bash
pg_dump -Fc --no-owner --no-acl "postgresql://user:haslo@<stary-serwer>:5432/prawdowid" > prawdowid.dump
pg_restore --no-owner --no-acl -d "$DATABASE_URL" prawdowid.dump   # DATABASE_URL_UNPOOLED
```

`pg_dump` musi być w wersji nie starszej niż serwer, z którego zrzucacie.

### Krok 5. Sprawdzenie

- `https://<projekt>.vercel.app/api/health` → `{"status":"ok"}` (sprawdza też bazę),
- strona: sprawdzenie dowolnego zdania; logi etapów w Vercel → Logs,
- panel: `https://<projekt>.vercel.app/admin`, logowanie kontem z kroku 3.

### Ograniczenia funkcji Vercela

Ustawione w `api/index.py`, każde da się nadpisać zmienną:

- Jedno sprawdzenie trwa najwyżej 300 s (`maxDuration`, maksimum na planie Hobby). Backend
  przerywa analizę po 280 s (`CHECK_TIMEOUT_SECONDS`) i zwraca 504 `analysis_timeout`.
- Dysk jest tylko do odczytu, poza `/tmp`. Logi (`LOG_FILE`) i ustawienia z panelu
  (`RUNTIME_CONFIG_FILE`) trafiają do `/tmp/prawdowid` i znikają razem z instancją. Logi są
  też w zakładce Logs na Vercelu.
  - Raport zagrożeń w panelu widzi tylko logi bieżącej instancji.
  - Zmiany ustawień z panelu (np. model) trzeba wpisać jako zmienne w Vercelu, żeby przetrwały.
- Limit równoległych sprawdzeń (`MAX_CONCURRENT_CHECKS`), cache źródeł i limity zapytań działają
  w obrębie jednej instancji, nie globalnie.
- Koszt modelu rośnie z liczbą sprawdzeń: ustawcie limit wydatków w panelu OpenAI (Settings →
  Limits).
