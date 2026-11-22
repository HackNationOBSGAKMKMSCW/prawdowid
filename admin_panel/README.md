# admin_panel — panel administracyjny Prawdowida

Frontend panelu dla administratora, analityka i moderatora: logowanie, pulpit
(co wymaga uwagi teraz), statystyki,
alerty i ostrzeżenia, luki informacyjne, powtarzające się zapytania, sprawy
moderatora, historia weryfikacji, katalog źródeł, wymienne modele, reguły
alertów, kanały i prywatność, użytkownicy oraz dziennik audytu.

Wszystko jest w tym folderze; główne `backend/` i `frontend/` nie są zmieniane.

```
admin_panel/
├── openapi.yaml          # kontrakt API panelu (do zaimplementowania w backendzie)
└── frontend/             # Vite + React 19 + TypeScript, port 5175
    ├── public/config.json   # konfiguracja uruchomieniowa (adres API, tryb danych)
    └── src/
        ├── config.ts        # wczytanie config.json → env → wartości domyślne
        ├── api/
        │   ├── types.ts         # modele domenowe (zgodne z openapi.yaml)
        │   ├── AdminApi.ts      # interfejs źródła danych
        │   ├── endpoints.ts     # ścieżki endpointów (nadpisywalne w config.json)
        │   ├── http.ts          # implementacja HTTP (Bearer, timeout, 401 → wylogowanie)
        │   ├── mock/            # dane przykładowe + referencyjne reguły wykrywania
        │   └── index.ts         # wybór implementacji na podstawie konfiguracji
        ├── auth/            # sesja, ochrona tras, role i uprawnienia
        ├── components/      # układ, UI, wykresy SVG, etykiety PL
        └── pages/           # widoki panelu
```

## Uruchomienie

```bash
cd admin_panel/frontend
npm install
npm run dev        # http://localhost:5175
```

Domyślnie panel działa w **trybie demonstracyjnym** (`"dataSource": "mock"`):
dane są generowane w przeglądarce, a panel pokazuje to w banerze. Konta
przykładowe (hasło `demo1234`):

| Konto | Rola | Co widzi |
|---|---|---|
| `admin@prawdowid.demo` | administrator | wszystko, w tym modele, reguły, użytkowników |
| `analityk@prawdowid.demo` | analityk | luki, źródła (edycja), modele (podgląd) |
| `moderator@prawdowid.demo` | moderator | alerty, sprawy, historia, źródła (podgląd) |

Zmiany wprowadzone w trybie demo są pamiętane w `localStorage` przez 6 godzin;
„Kanały i prywatność → Przywróć dane demo” zaczyna od nowa.

Build produkcyjny: `npm run build` → `dist/` (statyczne pliki).

## API nie jest zapisane w kodzie

Strony korzystają wyłącznie z interfejsu `AdminApi`. Implementację wybiera
konfiguracja, czytana w kolejności (późniejsze wygrywa):

1. wartości domyślne (`src/config.ts`),
2. zmienne z buildu: `VITE_ADMIN_DATA_SOURCE`, `VITE_ADMIN_API_URL` (`.env.example`),
3. `public/config.json`, pobierany przy starcie — można go podmienić na serwerze
   bez przebudowy.

```json
{
  "dataSource": "http",
  "apiBaseUrl": "https://api.example.gov.pl/admin",
  "requestTimeoutMs": 20000,
  "environmentLabel": "pilotaż",
  "endpoints": { "dashboard": "/stats/overview" }
}
```

`endpoints` pozwala nadpisać pojedyncze ścieżki (klucze w
`src/api/endpoints.ts`), gdy backend ma inne trasy. W trybie deweloperskim
względny `apiBaseUrl` (np. `/api/admin`) jest przekazywany przez proxy Vite na
`ADMIN_API_PROXY_TARGET` (domyślnie `http://127.0.0.1:8000`).

Kontrakt wszystkich endpointów jest w [`openapi.yaml`](openapi.yaml). Aby
podłączyć inny transport (np. GraphQL), wystarczy nowa klasa implementująca
`AdminApi` w `src/api/index.ts`.

## Modele łatwe do podmienienia

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

- Backend nie ma jeszcze endpointów z `openapi.yaml`; do tego czasu panel
  działa na danych przykładowych.
- Wszystkie liczby w trybie demo (w tym mierniki jakości) są przykładowe — nie
  są wynikami testów systemu.
- Uprawnienia w panelu tylko ukrywają akcje; egzekwować je musi serwer.
- Wykrywanie tematów wysokiego ryzyka w implementacji referencyjnej to
  dopasowanie słów kluczowych; backend może je zastąpić klasyfikatorem.
