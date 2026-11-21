# Prawdowid – frontend

Aplikacja webowa Prawdowida: użytkownik wkleja wiadomość albo link i dostaje
wynik z werdyktem dla każdego zdania oraz źródłami, które może sam przeczytać.
Interfejs według projektu „Prawdowid v4”.

React 19 + TypeScript + Vite, bez bibliotek UI. Czcionka Source Sans 3 jest
dołączona lokalnie (`@fontsource`), bez Google Fonts.

## Uruchomienie

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # kontrola typów + build produkcyjny do dist/
npm run lint
```

Domyślnie aplikacja działa na **danych przykładowych** (`VITE_API_MODE=mock`)
i nie potrzebuje backendu. Pasek „DEMO” na górze pokazuje wszystkie
scenariusze: wynik ze źródłami, analiza dat i manipulacji, link, opinia,
„napisz więcej”, „poza zakresem” i awaria.

Żeby łączyć się z backendem, ustaw w `.env.local` (wzór w `.env.example`):

```
VITE_API_MODE=live
```

W dev Vite przekierowuje `/api` na `http://127.0.0.1:8000`.

## Ekrany

| Ekran | Kiedy |
| --- | --- |
| Start | formularz, „Jak to działa”, legenda werdyktów, grupy źródeł |
| Sprawdzamy… | w trakcie zapytania |
| Wynik | karty zdań (werdykt, wyjaśnienie, źródła) i karty analizy (daty, manipulacja) |
| Napisz trochę więcej | backend zwrócił `clarify` |
| Tego nie sprawdzamy | backend zwrócił `out_of_scope` |
| Coś poszło nie tak | błąd sieci, błąd HTTP albo limit czasu (90 s) |

Podstrony: `/zrodla` (pełna lista źródeł), `/pomoc`, `/deklaracja-dostepnosci`.

Link `/?q=<tekst>` od razu sprawdza podany tekst – z tego korzysta przycisk
„Udostępnij wynik”.

## Kontrakt API

Typy są w [`src/api/types.ts`](src/api/types.ts).

### `POST /api/check`

```json
{ "text": "Szczepionki powodują autyzm." }
```

Odpowiedź – jeden z trzech wariantów:

```jsonc
// wynik
{
  "status": "result",
  "id": "abc123",                 // potrzebne do zgłoszenia błędu i usunięcia danych
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

// wiadomość za krótka / niejasna
{ "status": "clarify" }

// pytanie spoza zakresu
{ "status": "out_of_scope" }
```

### `POST /api/check/{id}/report` → `204`

Przycisk „Zgłoś błąd”.

### `DELETE /api/check/{id}` → `204`

Przycisk „Usuń moje dane”.

## Dostępność

- przełączniki „Większy tekst” (powiększenie 120%) i „Wysoki kontrast”,
  zapamiętane w `localStorage`;
- „Przeczytaj na głos” przez Web Speech API (`pl-PL`);
- link „Przejdź do treści”, fokus przenoszony na nagłówek po zmianie ekranu,
  komunikaty przez `aria-live`;
- obsługa `prefers-reduced-motion` i `forced-colors`.

## Struktura

```
src/
├── api/          kontrakt (types.ts), klient HTTP, dane przykładowe
├── components/   nagłówek, stopka, pasek demo, karty wyniku
├── content/      teksty werdyktów, lista źródeł
├── lib/          stan sprawdzania, nawigacja, mowa, preferencje, formatowanie
├── pages/        podstrony informacyjne
└── screens/      ekrany strony głównej
```
