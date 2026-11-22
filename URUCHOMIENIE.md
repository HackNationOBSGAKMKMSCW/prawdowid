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

## Wdrożenie

Strona, panel i backend działają w jednym projekcie Vercela z katalogu głównego repo
(`vercel.json`). Baza, model i API zewnętrzne są osobnymi usługami, osiągalnymi z internetu.

| Część | Gdzie na Vercelu | Adres |
|---|---|---|
| Strona | statyczny build `frontend/` (`npm run build:live`) | `/` |
| Panel admina | statyczny build `admin_panel/frontend/` | `/admin` |
| Backend (FastAPI) | funkcja `api/index.py`, limit 300 s | `/api/*` |

Strona i panel wołają `/api` w tej samej domenie, więc `VITE_API_BASE_URL` i `CORS_ORIGINS` nie
są potrzebne.

**Usługi zewnętrzne.** Funkcja Vercela nie widzi sieci prywatnej (Tailscale, LAN), więc każda
usługa musi mieć publiczny adres:

- **PostgreSQL** z TLS, np. Neon albo Supabase. Najlepiej adres poolera, bo funkcje otwierają
  wiele krótkich połączeń.
- **Model** z endpointem zgodnym z OpenAI, np. Gemini albo Ollama za tunelem z kluczem. Ollama
  nie ma uwierzytelnienia, więc nie wystawiaj jej publicznie bez proxy z kluczem.
- Google Fact Check i EUvsDisinfo: tylko klucze.

**Zmienne w Vercelu** (Settings → Environment Variables):

- `DATABASE_URL`;
- `FREELLM_BASE_URL`, `FREELLM_API_KEY`, `FREELLM_MODEL`;
- `GOOGLE_FACT_CHECK_API_KEY`;
- `EUVSDISINFO_API_KEY`;
- `ADMIN_USER_SALT`: losowy ciąg; bez niego pseudonimy w panelu używają publicznej soli
  domyślnej;
- opcjonalnie strojenie z `.env.example` (`ARTICLE_*`, `TRUSTED_*`, `MAX_CONCURRENT_CHECKS`).

Pliku `.env` nie ma we wdrożeniu (`.vercelignore`), więc wszystko ustawia się w Vercelu.

**Baza przed pierwszym wdrożeniem**, lokalnie z katalogu `backend/`, z `DATABASE_URL` nowej bazy:

```bash
python -m database migrate
python -m database seed-sources
python -m database create-user --email ... --name "..." --role admin
```

**Ograniczenia funkcji Vercela** (ustawione w `api/index.py`, każde da się nadpisać zmienną):

- Jedno sprawdzenie może trwać najwyżej 300 s (`maxDuration`, maksimum na planie Hobby).
  Backend przerywa analizę po 280 s (`CHECK_TIMEOUT_SECONDS`) i zwraca 504 `analysis_timeout`.
- Dysk jest tylko do odczytu, poza `/tmp`. Logi (`LOG_FILE`), ustawienia z panelu
  (`RUNTIME_CONFIG_FILE`) i zapasowy SQLite trafiają do `/tmp/prawdowid` i znikają razem z
  instancją. Logi są też w zakładce Logs na Vercelu.
  - Raport zagrożeń w panelu widzi tylko logi bieżącej instancji.
  - Zmiany ustawień z panelu trzeba wpisać jako zmienne w Vercelu, żeby przetrwały.
- Limit równoległych sprawdzeń (`MAX_CONCURRENT_CHECKS`), cache źródeł i limity zapytań działają
  w obrębie jednej instancji, nie globalnie.
