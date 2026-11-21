# Prawdowid – frontend

Aplikacja webowa Prawdowida z dwoma widokami, przełączanymi u góry ekranu:

- **Strona** (`/`) – użytkownik wkleja wiadomość albo link i dostaje wynik z
  werdyktem dla każdego zdania oraz źródłami. Interfejs według projektu „Prawdowid v4”.
- **WhatsApp** (`/whatsapp`) – symulator czatu z Prawdowidem
  (`src/whatsapp/`), rozmawia z adapterem z `whatsapp_sim/backend`. Nic nie trafia
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

| Ekran                | Kiedy                                                                         |
| -------------------- | ----------------------------------------------------------------------------- |
| Start                | formularz, „Jak to działa”, legenda werdyktów, grupy źródeł                   |
| Sprawdzamy…          | w trakcie zapytania                                                           |
| Wynik                | karty zdań (werdykt, wyjaśnienie, źródła) i karty analizy (daty, manipulacja) |
| Napisz trochę więcej | backend zwrócił `clarify`                                                     |
| Tego nie sprawdzamy  | backend zwrócił `out_of_scope`                                                |
| Coś poszło nie tak   | błąd sieci, błąd HTTP albo limit czasu (90 s)                                 |

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

Okno „Zgłoś błąd”:

```json
{ "reason": "bad_source", "comment": "Link do źródła nie działa." }
```

`reason`: `wrong_verdict` | `bad_source` | `misunderstood` | `other`; `comment` jest opcjonalny (do 1000 znaków).

## Dostępność

Cel: WCAG 2.2 na poziomie AA.

- przełączniki „Większy tekst” (ikona aA, powiększenie 120%) i „Wysoki kontrast”
  (ikona ◐), zapamiętane w `localStorage`; podpisy w dymkach da się najechać
  myszą i schować klawiszem Esc;
- „Przeczytaj na głos” przez Web Speech API (`pl-PL`);
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
| Kontrast całej palety (tekst ≥ 4,5:1, elementy interfejsu ≥ 3:1)                                                                                                           | wszystkie pary spełniają |
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
