# Wdrożenie demo na Vercelu (strona + panel + backend, baza Neon)

Wszystko działa w jednym projekcie Vercela z katalogu głównego repo:

| Część | Gdzie na Vercelu | Adres |
|---|---|---|
| Strona i symulator WhatsApp | statyczny build `frontend/` (`npm run build:live`) | `/`, `/whatsapp` |
| Panel admina | statyczny build `admin_panel/frontend/` (`--base=/admin/`) | `/admin` |
| Backend FastAPI (`backend/server.py`) | funkcja Pythona `api/index.py`, region `fra1`, limit 300 s | `/api/*` |
| PostgreSQL | Vercel → Storage → Neon (Frankfurt), prefiks `TEMP` | `TEMP_DATABASE_URL` → `DATABASE_URL` |

Konfiguracja projektu jest w plikach w repo, więc w panelu Vercela niczego nie trzeba wpisywać ręcznie:
- `vercel.json`: install, build, katalog wynikowy, funkcja i przekierowania;
- `api/index.py`: ścieżki Pythona i zapis na dysk do `/tmp`;
- `.python-version`: Python 3.14.

Strona i panel wołają `/api` pod tym samym adresem, więc `CORS_ORIGINS` i `VITE_API_BASE_URL` nie są potrzebne.

Na Neonie działa:
- `/api/health`;
- lista stron zaufanych;
- zgłoszenia ze strony;
- panel admina: logowanie, dziennik zapytań, tematy, luki, alerty i dziennik działań.

Panel trzyma wszystko w tej samej bazie Neon. Plik SQLite (`ADMIN_DB_PATH`) to tylko zapas na brak `DATABASE_URL`.

**Model językowy (LLM) jest na razie wyłączony:** „Sprawdź” na stronie kończy się komunikatem o błędzie (`502 analysis_failed`). Po dodaniu zmiennych `FREELLM_*` (krok 4) i redeployu sprawdzanie zacznie działać bez zmian w kodzie.

## Krok 1. Repozytorium

Vercel buduje z GitHuba, więc `vercel.json` i `api/index.py` muszą być na gałęzi `main`.

Na planie **Hobby** Vercel nie wdroży **prywatnego** repozytorium należącego do **organizacji** na GitHubie. Masz trzy wyjścia:
- upublicznić repo;
- użyć zespołu Pro (14 dni próbnych);
- wdrażać z CLI z własnego komputera: `npm i -g vercel`, a potem `vercel deploy --prod` w katalogu głównym repo. Plik `.vercelignore` pilnuje, żeby nie wysłać `.env` ani `.venv`.

## Krok 2. Nowy projekt

1. https://vercel.com/new → **Import Git Repository**. Wybierz repo `prawdowid`. Jeśli go nie widać, kliknij „Adjust GitHub App Permissions” i daj dostęp do organizacji.
2. Na ekranie konfiguracji ustaw:
   - **Project Name**: dowolna, np. `sprawdz-to-demo`. Od niej zależy adres `https://<nazwa>.vercel.app`.
   - **Framework Preset**: `Other`.
   - **Root Directory**: zostaw `./`, czyli katalog główny.
   - **Build and Output Settings**: nic nie zmieniaj. Wartości z `vercel.json` mają pierwszeństwo.
   - **Environment Variables**: na razie pusto, uzupełnisz je w kroku 4.
3. **Deploy**. Build strony i panelu powinien się udać. `/api/*` będzie zwracać błąd do czasu podpięcia bazy, to normalne.

## Krok 3. Baza Neon (Storage)

1. W projekcie otwórz zakładkę **Storage** → **Create Database** → **Neon** (Serverless Postgres) → **Continue**.
2. Ustaw:
   - **Region**: **Frankfurt, Germany (eu-central-1)**. Musi być blisko funkcji (`fra1`), bo backend wysyła do bazy wiele krótkich zapytań.
   - **Plan**: Free.
   - **Database name**: dowolna, np. `sprawdz-to`.
3. **Create**, a w oknie **Connect Project**:
   - **Environments**: zaznacz Production i Preview. Development jest potrzebny tylko dla `vercel env pull` w kroku 5, więc też go zaznacz.
   - **Custom Prefix**: `TEMP`. W projekcie są już bezprefiksowe zmienne bazy, które Vercel dodał wcześniej, a ten prefiks oddziela od nich nową bazę.
4. **Connect**. W **Settings → Environment Variables** pojawią się między innymi:
   - `TEMP_DATABASE_URL`: adres przez pooler, z niego korzysta aplikacja;
   - `TEMP_DATABASE_URL_UNPOOLED`: adres bez poolera, do migracji.

   Backend czyta tylko `DATABASE_URL`, dlatego `api/index.py` przy starcie funkcji wpisuje do niego `TEMP_DATABASE_URL` (albo `TEMP_POSTGRES_URL`). To ma pierwszeństwo przed starą, bezprefiksową `DATABASE_URL`.
   - W Logs pojawia się wtedy linia `[vercel] DATABASE_URL z TEMP_DATABASE_URL`, bez samego adresu.
   - Inny prefiks ustawiasz zmienną `DATABASE_ENV_PREFIX`.
   - Pusta `DATABASE_ENV_PREFIX` przywraca zwykłe `DATABASE_URL`.

Nic więcej przy bazie nie trzeba:
- SSL jest weryfikowany domyślnie, więc `DATABASE_SSL_MODE` zostaw puste;
- backend wycina z adresu `channel_binding=require`, którego asyncpg nie zna;
- połączenia nie używają nazwanych prepared statements, więc działają przez pooler Neona.

## Krok 4. Zmienne środowiskowe

**Settings → Environment Variables**, środowiska Production i Preview:

| Zmienna | Wartość | Po co |
|---|---|---|
| `ADMIN_USER_SALT` | losowy ciąg, np. `openssl rand -hex 32` albo `python -c "import secrets;print(secrets.token_hex(32))"` | pseudonimy użytkowników w dzienniku panelu |
| `SPRAWDZTO_MODE` | `demo` | symulator WhatsApp (`/whatsapp`) odpowiada przykładami bez LLM. Bez tego zwraca błąd tak jak strona. Usuń, gdy dodasz model |
| `GOOGLE_FACT_CHECK_API_KEY` | klucz Google Fact Check Tools (opcjonalnie) | dane z fact-checków |

Na później, gdy włączycie model:

| Zmienna | Wartość |
|---|---|
| `FREELLM_API_KEY` | klucz API modelu |
| `FREELLM_BASE_URL` | np. `https://api.openai.com/v1` |
| `FREELLM_MODEL` | np. `gpt-6.2-sol` |
| `LLM_REASONING_EFFORT` | `low` (gpt-6.2-sol odrzuca `none`) |
| `FREELLM_TIMEOUT` | `60` |
| `EUvsDisinfo_API_KEY` | klucz EUvsDisinfo (bez niego to sprawdzenie jest wyłączone) |

Zmiany zmiennych wchodzą dopiero po redeployu (krok 6).

## Krok 5. Tabele, strony zaufane i konto admina (raz, z własnego komputera)

Nowa baza Neon jest pusta, a te polecenia zakładają wszystko od zera: 9 migracji (13 tabel), 48 stron zaufanych i pierwsze konto admina. Starej bazy ani zrzutu nie potrzeba. Polecenia można bezpiecznie powtórzyć, bo zastosowane migracje i istniejące źródła są pomijane.

Migracje idą adresem **bez poolera** (`TEMP_DATABASE_URL_UNPOOLED`). Potrzebny jest Python z zależnościami z `requirements.txt`, np. `backend\.venv` (zob. `URUCHOMIENIE.md`, krok 1).

`vercel` CLI **nie jest potrzebne**. Pakiet `vercel` z `pip` to biblioteka Pythona, a nie CLI, więc do tego kroku się nie przyda.

### 5a. Skopiuj adres bazy (przeglądarka)

1. Vercel → projekt → **Storage** → kliknij bazę Neon.
2. W sekcji **Quickstart** wybierz zakładkę **.env.local** i kliknij **Show secret**.
3. Skopiuj wartość `TEMP_DATABASE_URL_UNPOOLED`, czyli tekst po `=` bez cudzysłowów. Wygląda tak: `postgresql://neondb_owner:...@ep-...eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`.
   - W nazwie hosta **nie ma** `-pooler`.
   - Jeśli widzisz tylko adres z `-pooler`, otwórz **Open in Neon** → **Connect**, wyłącz **Connection pooling** i skopiuj adres stamtąd.

### 5b. Uruchom polecenia (PowerShell)

Użyj terminala **PowerShell**, a nie Git Bash. W VS Code: Terminal → New Terminal, a potem strzałka obok `+` → PowerShell. W Git Bash programy pytające o odpowiedź (hasło, „Ok to proceed?”) nie przyjmują Entera: zamiast niego pojawia się `^M` albo litera.

```powershell
cd C:\Codes\projects\Hacknation\prawdowid\backend

# adres z kroku 5a, w POJEDYNCZYCH cudzysłowach (zawiera znak &)
$env:DATABASE_URL = 'postgresql://...wklej-tutaj...'

.\.venv\Scripts\python -m database check          # połączenie; migracje "DO ZASTOSOWANIA"
.\.venv\Scripts\python -m database migrate        # 9 migracji, 13 tabel
.\.venv\Scripts\python -m database seed-sources   # "Dodano 48 z 48 źródeł"
.\.venv\Scripts\python -m database create-user --email admin@example.pl --name "Jan Kowalski" --role admin
.\.venv\Scripts\python -m database check          # wszystkie migracje "zastosowana"

Remove-Item Env:DATABASE_URL                      # sprząta adres z tej sesji terminala
```

- `create-user` pyta o hasło: pisane znaki nie są widoczne, na końcu Enter. Hasło możesz też podać wcześniej: `$env:NEW_USER_PASSWORD = '...'`, a po wszystkim `Remove-Item Env:NEW_USER_PASSWORD`.
- Role: `admin` (pełna kontrola) i `analyst` (podgląd).
- Zmienna `$env:DATABASE_URL` ma pierwszeństwo przed lokalnym `.env`, więc polecenia idą do Neona, a nie do bazy z `.env`.
- Adres bazy zawiera hasło. Nie wklejaj go do plików w repo ani na czat.

### Opcjonalnie: przez `vercel` CLI

CLI to pakiet z npm, a nie z pip. W **PowerShell**:

```powershell
npm i -g vercel           # instalacja bez pytania "Ok to proceed?"
vercel login
cd C:\Codes\projects\Hacknation\prawdowid
vercel link               # zespół i projekt z kroku 2
vercel env pull .env.vercel --environment=production
$env:DATABASE_URL = ((Select-String -Path .env.vercel -Pattern '^TEMP_DATABASE_URL_UNPOOLED=').Line -replace '^TEMP_DATABASE_URL_UNPOOLED=', '').Trim('"')
Remove-Item .env.vercel
```

Dalej tak jak w 5b, od `cd backend`.

## Krok 6. Redeploy

**Deployments** → ostatnie wdrożenie → **⋯** → **Redeploy**. Odznacz „Use existing Build Cache”, jeśli zmienne miały trafić do builda. Każdy kolejny push na `main` wdraża się sam.

## Krok 7. Sprawdzenie

| Adres | Oczekiwany wynik |
|---|---|
| `https://<projekt>.vercel.app/api/health` | `{"status":"ok"}` (sprawdza też połączenie z bazą) |
| `https://<projekt>.vercel.app/` | strona; „Sprawdź” daje komunikat o błędzie, bo LLM jest wyłączony |
| `https://<projekt>.vercel.app/whatsapp` | symulator; przy `SPRAWDZTO_MODE=demo` odpowiada przykładem |
| `https://<projekt>.vercel.app/admin` | logowanie kontem z kroku 5; w dzienniku widać zapytania ze strony i WhatsAppa |

Logi backendu są w zakładce **Logs** projektu: każdy etap sprawdzania i błędy.

## Gdy coś nie działa

| Objaw | Przyczyna |
|---|---|
| `/api/health` zwraca 500, a w Logs jest `DATABASE_URL is required` | baza nie jest podpięta do tego środowiska (krok 3) albo nie było redeployu |
| W Logs jest `[vercel] brak TEMP_DATABASE_URL` | baza podpięta z innym prefiksem: ustaw `DATABASE_ENV_PREFIX` albo podepnij ją ponownie z prefiksem `TEMP` |
| Panel działa, ale nie widać w nim nowej bazy (stare dane albo błąd tabel) | funkcja łączy się ze starą bazą: sprawdź w Logs linię `[vercel] DATABASE_URL z ...` |
| `/api/health` zwraca 500, a w Logs jest `relation ... does not exist` | nie wykonano `migrate` (krok 5) |
| Nie da się zalogować do panelu | brak konta (`create-user`) albo migracji |
| Lista źródeł jest pusta | nie wykonano `seed-sources` |
| 404 na `/admin/...` po odświeżeniu | build bez `vercel.json` (zły Root Directory) |
| Build nie widzi repo | plan Hobby a prywatne repo organizacji (krok 1) |

## Ograniczenia funkcji Vercela (demo)

Wartości domyślne są ustawione w `api/index.py` i każdą da się nadpisać zmienną:
- **Czas.** Jedno sprawdzenie trwa najwyżej 300 s (`maxDuration`). Backend przerywa analizę po 280 s (`CHECK_TIMEOUT_SECONDS`) i zwraca 504.
- **Dysk.** Jest tylko do odczytu, poza `/tmp`. Plik logów (`LOG_FILE`) i ustawienia zmienione w panelu (`RUNTIME_CONFIG_FILE`) leżą w `/tmp/prawdowid` i znikają razem z instancją. Na stałe ustawia się je zmiennymi w Vercelu. Raport zagrożeń w panelu widzi tylko logi bieżącej instancji.
- **Instancje.** Limit równoległych sprawdzeń, cache źródeł i limity zapytań działają osobno w każdej instancji.
- **Praca w tle.** Zadania w tle (np. zapis zgłoszeń SQL injection) mogą się wykonać z opóźnieniem, gdy instancja jest uśpiona między żądaniami.
- **Zimny start.** Przy starcie instancji panel łączy się z bazą i czyści stare wpisy (retencja), więc pierwsze żądanie po przerwie trwa dłużej.
