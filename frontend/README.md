# Prawdowid – frontend

Aplikacja webowa Prawdowida z dwoma widokami, przełączanymi u góry ekranu:

- **Strona** (`/`) – użytkownik wkleja wiadomość albo link i dostaje wynik z
  werdyktem dla każdego zdania oraz źródłami. Interfejs według projektu „Prawdowid v4”.
- **WhatsApp** (`/whatsapp`) – symulator czatu z Prawdowidem
  (`src/whatsapp/`). Ten sam backend i ta sama weryfikacja co na stronie, wynik
  podany jak wiadomości czatu (`whatsapp_sim/backend`). Nic nie trafia
  do prawdziwego WhatsAppa. Numer na stronie startowej otwiera ten widok z
  wpisaną wiadomością (`/whatsapp?text=…`).

React 19 + TypeScript + Vite, bez bibliotek UI. Czcionka Source Sans 3 jest
dołączona lokalnie (`@fontsource`), bez Google Fonts.

## Uruchomienie

```bash
npm install
npm run dev        # http://localhost:5173
npm run dev:host   # to samo, ale dostępne też z telefonu w tej samej sieci Wi-Fi
npm run build      # kontrola typów + build produkcyjny do dist/
npm run lint
```

### Test na telefonie (Wi-Fi albo Tailscale)

- **Ta sama sieć Wi-Fi:** `npm run dev:host`, potem na telefonie adres `Network`
  z terminala, np. `http://192.168.1.23:5173`.
- **Tailscale, adres IP:** `npm run dev:host`, potem `http://100.x.y.z:5173`
  (IP Maca z aplikacji Tailscale).
- **Tailscale z HTTPS (zalecane):** `npm run dev` (bez `--host`) i w drugim
  terminalu `tailscale serve --bg 5173`. Strona jest pod
  `https://<nazwa-maca>.<tailnet>.ts.net` tylko w Twoim tailnecie. HTTPS jest
  potrzebny m.in. do kopiowania linku przez schowek. Wyłączenie:
  `tailscale serve --https=443 off`.

Domeny `.ts.net` są dopuszczone w `vite.config.ts` (`allowedHosts`).

Domyślnie aplikacja działa na **danych przykładowych** (`VITE_API_MODE=mock`)
i nie potrzebuje backendu. Pasek „DEMO” na górze pokazuje wszystkie
scenariusze: wynik ze źródłami, analiza dat i manipulacji, link, opinia,
„napisz więcej”, „poza zakresem” i awaria.

### Z prawdziwym backendem

Jeden backend i frontend w trybie `live` (każde w osobnym terminalu, z
katalogu głównego repo):

```bash
# 1. backend: strona (/api/check, /api/check/{id}/report, /api/health, /api/trusted-sources)
#    i symulator WhatsApp (/api/whatsapp/*), ta sama weryfikacja dla obu
#    (DATABASE_URL i klucze modeli w głównym .env, wzór: .env.example; zob. backend/API.md)
PYTHONPATH=backend:analysis:analysis/src uvicorn server:app --port 8000

# 2. frontend połączony z backendem
cd frontend && npm run dev:live    # http://localhost:5173
```

Zamiast `npm run dev:live` można ustawić `VITE_API_MODE=live` w głównym `.env` projektu.
Vite przekazuje całe `/api` na port 8000 (`API_PROXY_TARGET` w głównym `.env`, wzór w
głównym `.env.example`). Osobny adapter WhatsApp, np. offline demo
(`cd whatsapp_sim/backend && python -m whatsappAdapter --demo`, port 8001), włącza się
przez `WHATSAPP_PROXY_TARGET=http://127.0.0.1:8001`.
`npm run build:live` buduje stronę w trybie `live`; na serwerze `/api` musi
prowadzić do `server:app` (ta sama domena albo `VITE_API_BASE_URL` + `CORS_ORIGINS`).

W trybie `live`:
- strona startowa pyta `GET /api/health` i ostrzega, gdy serwer nie działa;
- błędy z backendu (`invalid_url`, `unsafe_url`, `url_unavailable`,
  `analysis_busy`, `analysis_timeout`, …) mają własne komunikaty, a przy
  problemach z treścią „Popraw wiadomość” wraca do formularza z tekstem;
- „Lista źródeł” pochodzi z `GET /api/trusted-sources` (te same źródła, które
  przeszukuje weryfikacja); bez serwera zostaje lista z kodu;
- „Zgłoś błąd” zapisuje zgłoszenie w bazie (`POST /api/check/{id}/report`).

## Ekrany

| Ekran                | Kiedy                                                                         |
| -------------------- | ----------------------------------------------------------------------------- |
| Start                | formularz, „Jak to działa”, legenda werdyktów, grupy źródeł                   |
| Sprawdzamy…          | w trakcie zapytania                                                           |
| Wynik                | karty zdań (werdykt, wyjaśnienie, źródła) i karty analizy (daty, manipulacja) |
| Napisz trochę więcej | backend zwrócił `clarify`                                                     |
| Tego nie sprawdzamy  | backend zwrócił `out_of_scope`                                                |
| Coś poszło nie tak   | błąd sieci, błąd HTTP albo limit czasu; komunikat zależy od kodu błędu API    |

Podstrony: `/zrodla` (pełna lista źródeł), `/pomoc`, `/deklaracja-dostepnosci`.

Lista źródeł (`/zrodla` i skrót na stronie startowej) pochodzi z bazy:
`GET /api/trusted-sources`, czyli tabela `trusted_sources` edytowana w panelu admina.
Gdy serwer nie odpowiada, strona pisze, że listy nie da się pobrać; nie ma zapasowej
listy w kodzie. Tylko tryb `mock` pokazuje przykładową listę (`src/content/sources.ts`).

Link `/?q=<tekst>` od razu sprawdza podany tekst.

## Kontrakt API

Typy są w [`src/api/types.ts`](src/api/types.ts).

### `GET /api/check?text=...`

```http
GET /api/check?text=Szczepionki%20powoduj%C4%85%20autyzm.
```

W kodzie klienckim parametr `text` jest kodowany przez `URLSearchParams`.
Każde wywołanie uruchamia nową analizę. Tekst jest częścią adresu GET, więc nie
przekazuj w nim sekretów ani wrażliwych danych.

Odpowiedź po ukończonej analizie:

```jsonc
// wynik
{
  "status": "result",
  "id": "abc123",                 // potrzebne do zgłoszenia błędu
  "input_type": "text",           // albo "url"
  "claims": [
    {
      "verdict": "false",         // confirmed | false | misleading | insufficient | unverifiable
      "text": "Szczepionki powodują autyzm.",
      "explanation": "Duże badania setek tysięcy dzieci nie wykazały…",
      "sources": [
        { "quote": "…", "publisher": "NIZP PZH", "url": "https://…", "year": "2024", "lang": "pl" }
      ]
    }
  ],
  "analysis": {                   // opcjonalnie
    "manipulation": { "manipulation_detected": true, "score": 26, "fragments": [ … ] },
    "dates": { "dates_consistent": false, "issues": [ … ], "extracted": [ … ] }
  },
  "source_names": { "pap": "Polska Agencja Prasowa" }   // opcjonalnie, dla dates.issues[].source_id
}

```

### `POST /api/check/{id}/report` → `204`

Okno „Zgłoś błąd”:

```json
{ "reason": "bad_source", "comment": "Link do źródła nie działa." }
```

`reason`: `wrong_verdict` | `bad_source` | `misunderstood` | `other`; `comment` jest opcjonalny (do 1000 znaków).

Backend początkowo zwraca `result` dla ukończonej analizy. Błędne dane i awarie
zwracają odpowiedzi HTTP z kodem błędu; nie są przedstawiane jako `clarify` ani
`out_of_scope`, dopóki reguły tych klasyfikacji nie zostaną zdefiniowane.

### Produkcyjne połączenie z API

Frontend pozostaje hostowany na Vercel, a API działa jako osobna usługa FastAPI
na Render (konfiguracja w `render.yaml`). W ustawieniach builda Vercel ustaw:

```text
VITE_API_MODE=live
VITE_API_BASE_URL=https://<adres-api-render>/api
VITE_CHECK_TIMEOUT_MS=360000
```

W Render ustaw `CORS_ORIGINS` na dokładne originy frontendu (bez ścieżki),
`DATABASE_URL` na istniejącą bazę PostgreSQL oraz wymagane klucze/model LLM.
`REPORT_RETENTION_DAYS` steruje retencją identyfikatorów wyników i zgłoszeń;
codzienny cron usuwa wygasłe rekordy.

## Dostępność

Cel: WCAG 2.2 na poziomie AA.

- przełączniki „Większy tekst” (ikona aA, powiększenie 120%), „Ciemny motyw”
  (ikona księżyca, domyślnie według systemu) i „Wysoki kontrast” (ikona ◐),
  zapamiętane w `localStorage`; motyw jest w `<html data-theme>` i ustawia się
  przed pierwszym renderem, więc strona nie mruga; podpisy w dymkach da się najechać
  myszą i schować klawiszem Esc;
- „Czytaj stronę na głos” (ikona głośnika w nagłówku, zapamiętane w `localStorage`):
  syntezator mowy przeglądarki (Web Speech API, `pl-PL`) czyta treść `<main>`, a po
  każdej zmianie strony lub ekranu (np. przejście na wynik) czyta nową treść sam;
  treść idzie blok po bloku (nagłówek, akapit, punkt listy, przycisk) z ciszą
  między nimi: 1 s po nagłówku, 0,65 s po innym bloku (stałe w `SpeechProvider.tsx`);
  Esc przerywa czytanie; po odświeżeniu strony przeglądarka pozwala mówić dopiero
  po pierwszym kliknięciu lub klawiszu, więc czytanie rusza wtedy;
- „Przeczytaj na głos” pod wynikiem czyta sam wynik (ten sam syntezator);
- link „Przejdź do treści”, fokus przenoszony na nagłówek `h1` po zmianie ekranu,
  komunikaty przez `aria-live`, błędy formularza przez `role="alert"`;
- okna modalne na `<dialog>`: fokus krąży tylko w oknie, Esc zamyka, fokus wraca
  na przycisk, który okno otworzył;
- źródła po angielsku mają `lang="en"`, cała strona `lang="pl"`;
- obsługa `prefers-reduced-motion` (bez animacji) i `forced-colors`.

### Co zostało sprawdzone

| Test                                                                                                                                                                       | Wynik                    |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| axe-core 4.10 (WCAG 2.0/2.1/2.2 A i AA + dobre praktyki), 13 stanów × komputer i telefon: start, błąd pola, wynik, analiza, awaria, okna, Pomoc, wysoki kontrast, WhatsApp | 0 błędów                 |
| Kontrast całej palety, jasnej i ciemnej (tekst ≥ 4,5:1, elementy interfejsu ≥ 3:1)                                                                                         | wszystkie pary spełniają |
| axe-core w ciemnym motywie, te same stany                                                                                                                                  | 0 błędów                 |
| Klawiatura: kolejność Tab, widoczny fokus na każdym elemencie, brak pułapek                                                                                                | OK                       |
| Powiększenie 200% i 400% (szerokość 640 i 320 px), bez przewijania w poziomie (1.4.10)                                                                                     | OK                       |
| Zwiększone odstępy tekstu (1.4.12)                                                                                                                                         | OK                       |
| Fokus nie chowa się pod przyciskiem demo w rogu (2.4.11)                                                                                                                   | OK                       |

**Nie zostało sprawdzone:** testy z prawdziwymi czytnikami ekranu (NVDA, JAWS,
VoiceOver, TalkBack) i z udziałem użytkowników. Automatyczne narzędzia wykrywają
tylko część problemów, więc przed wdrożeniem potrzebny jest ręczny audyt.

## Struktura

```
src/
├── api/          kontrakt (types.ts), klient HTTP, dane przykładowe
├── components/   nagłówek, stopka, pasek demo, karty wyniku
├── content/      teksty werdyktów, lista źródeł
├── lib/          stan sprawdzania, nawigacja, mowa, preferencje, formatowanie
├── pages/        podstrony informacyjne
├── screens/      ekrany strony głównej
└── whatsapp/     widok WhatsApp: symulator czatu
```
