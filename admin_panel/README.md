# admin_panel — panel administracyjny Prawdowida

Frontend panelu dla administratora i analityka: logowanie, pulpit
(co wymaga uwagi teraz), statystyki,
alerty i ostrzeżenia, luki informacyjne, powtarzające się zapytania, sprawy
moderatora, historia weryfikacji, katalog źródeł, wymienne modele, reguły
alertów, kanały i prywatność, użytkownicy oraz dziennik audytu.

Panel jest podłączony do backendu admina z `backend/admin` (FastAPI, `/api/admin`).
Bez backendu działa w trybie demonstracyjnym na danych przykładowych.

```
admin_panel/
├── openapi.yaml          # pierwotny kontrakt (tryb demo); prawdziwe API: backend/admin/api.py
└── frontend/             # Vite + React 19 + TypeScript, port 5175
    ├── public/config.json   # konfiguracja uruchomieniowa (adres API, ścieżki)
    └── src/
        ├── config.ts        # wczytanie config.json → env → wartości domyślne
        ├── api/
        │   ├── types.ts         # modele domenowe panelu
        │   ├── AdminApi.ts      # interfejs źródła danych + capabilities
        │   ├── endpoints.ts     # ścieżki backend/admin (nadpisywalne w config.json)
        │   ├── http.ts          # klient backend/admin (logowanie, token sesji, 401 → wylogowanie)
        │   ├── backend/         # surowe odpowiedzi backendu i ich mapowanie na typy panelu
        │   ├── mock/            # dane przykładowe + referencyjne reguły wykrywania
        │   └── index.ts         # wybór implementacji na podstawie konfiguracji
        ├── auth/            # sesja, ochrona tras, role i uprawnienia
        ├── components/      # układ, UI, wykresy SVG, etykiety PL
        └── pages/           # widoki panelu
```

## Uruchomienie z backendem

Backend potrzebuje Pythona ≥ 3.11 i bazy PostgreSQL (`DATABASE_URL` w `backend/.env`,
szczegóły w `backend/database/README.md`).

```bash
# 1. baza: tabele i pierwsze konto administratora (z katalogu backend/)
cd backend
python -m database migrate
python -m database create-user --email admin@example.pl --name "Jan Kowalski" --role admin

# 2. API strony razem z panelem (port 8000): /api/check, /api/admin, /api/trusted-sources
uvicorn server:app --port 8000

# 3. panel (Vite przekazuje /api na 127.0.0.1:8000)
cd admin_panel/frontend
npm install
npm run dev        # http://localhost:5175
```

**Logowanie** to e-mail i hasło konta z tabeli `users`:
- Hasła są w bazie jako skróty `scrypt`. Tokeny sesji są w `auth_access_tokens` jako SHA-256, a sam token zna tylko przeglądarka.
- Po kilku nieudanych próbach backend czasowo blokuje logowanie (429).
- Sesja wygasa po czasie z backendu albo przy odpowiedzi 401.

**Role** panelu to administrator i analityk (rola moderatora jest na razie wyłączona; migracja `0007` zmienia istniejące konta moderatorów na analityków). Sprawdza je backend (`backend/accounts/permissions.py`), a panel tylko chowa niedostępne widoki.
- **Administrator** ma pełną kontrolę nad panelem: modele, źródła, reguły, konta i hasła.
- **Analityk** ma panel obserwacyjny: widzi pulpit, statystyki, alerty, luki, historię weryfikacji, logi i źródła, może eksportować dane, ale niczego nie zmienia.

Strona dla obywateli nie ma kont: sprawdzanie jest anonimowe. Konta zakłada wyłącznie administrator.

**Bez danych o użytkownikach aplikacji.** Panel nie zbiera i nie pokazuje numerów telefonów,
adresów IP, pseudonimów ani innych identyfikatorów osób pytających (strona i WhatsApp). Reguły
liczą zapytania, a alert o treściach niebezpiecznych jest zbiorczy. Wyjątek: próba prompt
injection ze strony blokuje adres IP (domyślnie od 1. próby na 24 h). Panel pokazuje wtedy
tylko maskę adresu (`203.0.113.x`), a administrator może go odblokować w alercie albo w
„Zagrożeniach”. Widok **Konta panelu** pokazuje tylko konta panelu (administrator, analityk).

**Konta i hasła:**
- Konta zakłada i wyłącza administrator w widoku **Konta panelu** („Dodaj konto”, domyślnie rola analityka). Formularz generuje losowe hasło początkowe; administrator kopiuje je i przekazuje tej osobie razem z adresem e-mail. Może też ustawić komuś nowe hasło.
- Każdy zmienia własne hasło ikoną kłódki w górnym pasku. Zmiana wylogowuje wszystkie jego sesje.

**Dziennik audytu** (`activity_logs`) pokazuje logowania do panelu (także nieudane, z adresem IP), zmiany kont panelu, alerty, luki, źródła i konfigurację.

Bez `DATABASE_URL` backend działa na SQLite, ale bez kont, więc logowanie w panelu się nie uda.

Bot WhatsApp i panel muszą korzystać z tej samej bazy, żeby panel widział
zapytania z bota. Logi techniczne panel czyta z `LOG_FILE` (domyślnie
`backend/logs/app.jsonl`).

Inny adres backendu w trybie deweloperskim: `ADMIN_API_PROXY_TARGET` w `.env`
(`.env.example`). Po buildzie: `apiBaseUrl` w `public/config.json`.

### Co panel pokazuje z backendu

| Widok | Endpointy `backend/admin` |
|---|---|
| Pulpit, Statystyki | `GET /dashboard`, `GET /queries` (szereg czasowy, kanały, czasy odpowiedzi) |
| Alerty i ostrzeżenia | `GET /alerts`, `POST /alerts/{id}` (przyjęcie, rozwiązanie, odrzucenie), `POST /ip-blocks/{key}/block` i `/unblock` |
| Zagrożenia: zablokowane adresy | `GET /ip-blocks?active=true`, `POST /ip-blocks/{key}/unblock` |
| Luki informacyjne | `GET /info-gaps`, `GET /topics/{id}`, `POST /info-gaps/{id}` (podejrzenie → aktywna → w uzupełnianiu → zamknięta / odrzucona) |
| Historia weryfikacji | `GET /queries` (filtry: wynik, flaga, okres, tekst), `GET /queries/{id}` |
| Logi techniczne | `GET /events`, `GET /events/summary` |
| Modele i źródła danych | `GET`/`PATCH /config` (model, endpoint, klienci apiReading, pobieranie artykułów, klucze API tylko do zapisu), `GET /config/models` |
| Reguły i progi | `PATCH /config` (sekcja `monitoring`), `POST /maintenance/purge` |
| Logowanie, konto | `POST /auth/login`, `/auth/logout`, `GET /auth/me`, `POST /auth/me/password` |
| Konta panelu (bez kont aplikacji) | `GET`/`POST /accounts`, `PATCH /accounts/{id}`, `POST /accounts/{id}/password` |
| Dziennik audytu | `GET /activity` (bez bazy: `GET /config/audit`) |
| Strony zaufane | `GET`/`POST`/`PATCH`/`DELETE /sources`, `GET /sources/status`, `POST /sources/check` |
| Historia weryfikacji: zgłoszenia | `GET /queries?flag=zgloszenie`, pole `report` w `GET /queries/{id}` |

Panel jest częścią API strony (`server:app`), więc widzi sprawdzenia ze strony WWW
(kanał „WWW”) i z bota WhatsApp, zgłoszenia błędów z przycisku „Zgłoś błąd”, a zmiany
modeli i stron zaufanych od razu działają w weryfikacji.

Widoki z pierwotnego kontraktu, których backend nie ma (sprawy moderatora,
katalog źródeł w formie z demo, rejestr dostawców modeli, kanały, dziennik
bezpieczeństwa, powtarzające się zapytania), są ukryte. Każde źródło danych
deklaruje w `capabilities`, co obsługuje; menu, trasy i przyciski się do tego
dostosowują.

## Tryb demonstracyjny (bez backendu)

```bash
npm run dev:demo   # dane generowane w przeglądarce
```

Konta przykładowe (hasło `demo1234`):

| Konto | Rola | Co widzi |
|---|---|---|
| `admin@sprawdz.to.demo` | administrator | wszystko, w tym modele, reguły, użytkowników |
| `analityk@sprawdz.to.demo` | analityk | panel obserwacyjny: wszystko do odczytu, eksport |

Zmiany wprowadzone w trybie demo są pamiętane w `localStorage` przez 6 godzin;
„Kanały i prywatność → Przywróć dane demo” zaczyna od nowa.

Build produkcyjny: `npm run build` → `dist/` (statyczne pliki, backend admina);
`npm run build:demo` — wersja demonstracyjna.

## Konfiguracja nie jest zapisana w kodzie

Strony korzystają wyłącznie z interfejsu `AdminApi`. Implementację wybiera
konfiguracja, czytana w kolejności (późniejsze wygrywa):

1. wartości domyślne (`src/config.ts`: `http`, `/api/admin`),
2. zmienne z buildu: `VITE_ADMIN_DATA_SOURCE`, `VITE_ADMIN_API_URL` (`.env.example`,
   `.env.demo`),
3. `public/config.json`, pobierany przy starcie — można go podmienić na serwerze
   bez przebudowy.

```json
{
  "dataSource": "http",
  "apiBaseUrl": "https://api.example.gov.pl/api/admin",
  "requestTimeoutMs": 20000,
  "environmentLabel": "pilotaż",
  "endpoints": { "dashboard": "/dashboard" }
}
```

`endpoints` pozwala nadpisać pojedyncze ścieżki (klucze w
`src/api/endpoints.ts`), gdy backend ma inne trasy. Gdy panel i API są na
różnych domenach, backend musi zezwolić na CORS; najprościej podać panel i API
z jednej domeny (reverse proxy `/api/admin` → backend).

## Modele łatwe do podmienienia

> Ten i dwa kolejne rozdziały opisują pełny kontrakt z `openapi.yaml`, widoczny
> w trybie demo. Z backendem admina modele zmienia się w widoku **Modele i
> źródła danych**, a progi alertów w **Reguły i progi**.

Widok **Modele AI** odpowiada wymaganiu „wymiana modelu lub dostawcy
bez przebudowy systemu”:

- każdy etap potoku (rozpoznawanie twierdzeń, formułowanie odpowiedzi,
  wyszukiwanie semantyczne, OCR, transkrypcja, wcześniejsze wystąpienia obrazu)
  ma model główny, modele zapasowe i parametry (limit czasu, ponowienia, temperatura);
- rejestr dostawców: protokół (API zgodne z OpenAI, Anthropic, Google, Ollama,
  własny adapter), adres, **miejsce przetwarzania** (PL / EOG / poza EOG /
  własna infrastruktura), koszt, stan, test połączenia;
- klucze API nigdy nie trafiają do przeglądarki — panel zna tylko nazwę sekretu
  po stronie serwera (`keyRef`) i to, czy jest ustawiony; bez klucza nie da się
  przełączyć na danego dostawcę;
- przełączenie na dostawcę spoza EOG pokazuje ostrzeżenie; każda zmiana trafia
  do dziennika audytu.

## Alerty: luki informacyjne, terroryzm, powtarzające się pytania

Reguły są jawne i edytowalne w widoku **Reguły alertów** (referencyjna
implementacja: `src/api/mock/detection.ts`, do przeniesienia do backendu):

| Alert | Kiedy powstaje (domyślnie) |
|---|---|
| **Luka informacyjna** | ≥ 5 podobnych zapytań w 24 h, z czego ≥ 60% bez wystarczających dowodów |
| **Dużo zapytań o to samo** | ≥ 8 zapytań w 24 h i wzrost ≥ ×2,5 względem poprzednich 24 h |
| **Temat wysokiego ryzyka** | dopasowanie do listy tematów (terroryzm, bezpieczeństwo państwa i infrastruktura krytyczna, ewakuacja / sytuacje kryzysowe, wybory) — powiadomienie od pierwszego zapytania |
| **Prompt injection** | ≥ 3 próby w ciągu godziny |
| **Znany incydent** | treść podobna do przypadku z bazy incydentów — tylko kontekst, nie werdykt |
| **Status źródła** | zgłoszenia z domeny objętej np. sankcjami UE — neutralne ostrzeżenie |
| **Problem techniczny** | ≥ 3 awarie w 6 h — raportowane osobno, nigdy jako werdykt |

Alert nie jest werdyktem. Powiadomienie dostają osoby wskazane przez
administratora dla danego typu alertu. Gdy nikt nie jest wskazany, panel
pokazuje tylko **rekomendację** („nic nie zostało wysłane”).

Z alertu lub luki tworzy się **sprawę moderatora**: jedna sprawa na grupę
podobnych zapytań (kolejne alerty ją aktualizują zamiast tworzyć duplikaty).
Sprawa rozdziela **rekomendację przekazania** od **faktycznego przekazania**
konkretnej osobie. Zamknięcie sprawy wymaga opisu rozstrzygnięcia.

## Pozostałe wymagania z dokumentu

- **Historia weryfikacji**: pytanie (z zamaskowanymi danymi osobowymi), czas,
  kanał, wynik, siła podstaw, źródła (tytuł, wydawca, data publikacji i
  pobrania, link, fragment), uzasadnienie oddzielone od materiałów, modele,
  tokeny, koszt; usunięcie zapisu na żądanie.
- **Katalog źródeł**: typ, poziom zaufania A/B/C, licencja, uzasadnienie
  kwalifikacji, zawieszanie/wykluczanie z uzasadnieniem, kontrola minimów
  korpusu (≥ 100 dokumentów, ≥ 10 domen, ≥ 2 typy).
- **Pulpit**: to, co wymaga reakcji — krytyczne i pilne alerty (z przyciskami
  „Utwórz sprawę” / „Przyjmij”), luki informacyjne bez sprawy, sprawy czekające
  na przekazanie, problemy z modelami i źródłami, krótkie podsumowanie 24 h.
- **Statystyki** (osobna zakładka): ruch, odsetek wstrzymań, czas odpowiedzi,
  koszt na 1000 sprawdzeń, rozkład werdyktów, kanały, najczęstsze tematy.
- **Bezpieczeństwo**: dziennik prompt injection, SSRF, limitów, odrzuconych
  wejść i nieudanych logowań.
- **Prywatność**: maskowanie danych osobowych, retencja, anonimizacja,
  domyślnie bez archiwizacji pełnych treści, usunięcie danych sesji demo.
- **Eksport** CSV (z ochroną przed formułami) i JSON z każdej listy.
- **Logowanie**: limit 5 prób z blokadą 30 s po stronie przeglądarki (serwer
  musi mieć własny limit), sesja w `sessionStorage`, automatyczne wylogowanie
  po wygaśnięciu lub odpowiedzi 401, trasy chronione rolami.
- **Dostępność**: responsywny układ (menu wysuwane na telefonie), tryb jasny i
  ciemny, kontrast, obsługa klawiatury, etykiety tekstowe przy kolorach.

## Ograniczenia

- Backend zapisuje tylko liczbę źródeł, bez ich listy, uzasadnień, tokenów i
  kosztu pojedynczego sprawdzenia — panel pokazuje to, co jest (szczegóły
  żądania są w logach technicznych, po `request_id`).
- Szereg czasowy na pulpicie jest liczony z maks. 5000 zapytań z okresu.
- Backend ma już listę stron zaufanych (`/sources`, tabela `trusted_sources`),
  ale widok „Katalog źródeł” w panelu nie jest jeszcze pod nią podpięty.
- W trybie demo wszystkie liczby (w tym mierniki jakości) są przykładowe — nie
  są wynikami testów systemu.
