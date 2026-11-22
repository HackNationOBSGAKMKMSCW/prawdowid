# Powiadomienia admina: rosyjska dezinformacja i SQL injection

Oba zdarzenia trafiają do tej samej tabeli powiadomień co pozostałe alerty panelu (`monitor_alerts`). Front czyta je istniejącymi endpointami `/api/admin/alerts`. Schemat bazy się nie zmienił: kolumna `type` przyjmuje nowe wartości bez migracji.

| `type` | Kiedy powstaje | `subject` | Ważność |
|---|---|---|---|
| `rosyjska_dezinformacja` | twierdzenie z zapytania na stronie jest w bazie EUvsDisinfo (sprawdzenie przez MCP i potwierdzenie przez LLM) | skrót linku do przypadku: jeden alert na przypadek | `wysoka` |
| `sql_injection` | w parametrach URL, treści JSON lub formularza albo w wiadomości bota wykryto składnię SQL injection | `kanal:web`, `kanal:panel` albo `kanal:whatsapp` | `wysoka` |

## Jak liczone są wystąpienia

- Dopóki alert jest otwarty (`otwarty` albo `w_analizie`), każde kolejne wykrycie zwiększa `count`, aktualizuje `last_seen` i dopisuje wpis na początek `details.wystapienia` (maks. 20 ostatnich).
- Gdy admin zmieni stan na `rozwiazany` albo `falszywy_alarm`, następne wykrycie otwiera **nowy** alert.
- Alerty nie zawierają danych o osobach: nie ma numeru, adresu IP ani pseudonimu. `users` jest zawsze 0, `details.zrodla` jest puste, a `count` liczy każde zapytanie lub żądanie osobno.
- Jedno żądanie to jedno wystąpienie, nawet gdy składnię wykryją oba mechanizmy: middleware HTTP (pola żądania) i monitor treści (`tresc_wiadomosci`). Wystąpienia łączą się po `request_id`, a `pola` zawierają wtedy oba miejsca.
- SQL injection **niczego nie blokuje**. Zapytania do bazy są parametryzowane, więc to tylko powiadomienie.
- Skan i zapis alertu odbywają się w tle, po przyjęciu żądania, więc alert pojawia się w panelu z opóźnieniem rzędu milisekund. Przy zalewie prób (np. skaner podatności) nadmiarowe zgłoszenia są pomijane, zamiast przeciążać bazę.
- W alercie nie ma wartości pól, bo mogłoby to być np. hasło. Są tylko nazwy wzorców i pól.

## Odczyt

```http
GET /api/admin/alerts?type=rosyjska_dezinformacja&status=otwarty
GET /api/admin/alerts?type=sql_injection
GET /api/admin/alerts/{id}
POST /api/admin/alerts/{id}   {"status": "w_analizie" | "rozwiazany" | "falszywy_alarm", "note": "…"}
```

Uprawnienia: odczyt wymaga `alerts:read`, a zmiana stanu `alerts:write`.

Alerty widać też w `GET /api/admin/dashboard`: w `open_alerts` (liczba według typu) i w `latest_alerts`.

### `rosyjska_dezinformacja`

```jsonc
{
  "id": "47bf1d732b5b",
  "type": "rosyjska_dezinformacja",
  "subject": "b9a5b9886735535d",
  "severity": "wysoka",
  "status": "otwarty",
  "title": "Zweryfikowana rosyjska dezinformacja: NATO is preparing to attack Russia",
  "count": 1,                         // ile zapytań trafiło w ten przypadek
  "users": 1,
  "first_seen": "2026-11-22T04:34:44.557Z",
  "last_seen": "2026-11-22T04:34:44.557Z",
  "details": {
    "zrodlo": "EUvsDisinfo",
    "przypadek": {"tytul": "NATO is preparing to attack Russia",
                  "url": "https://euvsdisinfo.eu/report/nato-is-preparing-to-attack-russia-2"},
    "opis": "Użytkownik zapytał o twierdzenie, które baza EUvsDisinfo dokumentuje jako prokremlowską dezinformację.",
    "wystapienia": [{
      "ts": "2026-11-22T04:34:44.557Z",
      "request_id": "95151a60739b4caa",
      "query_id": "fbb4a7854bfb",     // -> GET /api/admin/queries/{query_id}
      "kanal": "web",
      "twierdzenie": "NATO przygotowuje atak na Rosję z terytorium Polski.",
      "uzasadnienie": "Ta sama teza: NATO szykuje napaść na Rosję."
    }],
    "zrodla": ["zapytanie:fbb4a7854bfb"]
  },
  "note": null,
  "updated_at": "2026-11-22T04:34:44.557Z"
}
```

Zapytanie powiązane z alertem ma flagę `rosyjska_dezinformacja`, więc da się je filtrować przez `GET /api/admin/queries?flag=rosyjska_dezinformacja`.

### `sql_injection`

```jsonc
{
  "id": "76b6a55a7a50",
  "type": "sql_injection",
  "subject": "kanal:panel",
  "severity": "wysoka",
  "status": "otwarty",
  "title": "Próby SQL injection (panel)",
  "count": 1,                         // liczba prób
  "users": 1,                         // różne źródła
  "details": {
    "kanal": "panel",
    "opis": "Wykryto składnię SQL injection w danych wejściowych. …",
    "wystapienia": [{
      "ts": "2026-11-22T04:34:45.054Z",
      "request_id": "95151a60739b4caa",   // -> GET /api/admin/events?request_id=…
      "wzorce": ["tautologia"],
      "pola": ["body.password"],          // query.<nazwa>, body.<ścieżka>, form.<nazwa>, sciezka, tresc_wiadomosci
      "metoda": "POST",
      "sciezka": "/api/admin/auth/login",
      "query_id": null                    // ustawione dla wiadomości z bota
    }],
    "zrodla": []                          // zawsze puste: bez danych o nadawcy
  }
}
```

Etykiety wzorców do pokazania w UI:

| Wzorzec | Etykieta |
|---|---|
| `union_select` | UNION SELECT |
| `tautologia`, `tautologia_z_komentarzem` | Warunek zawsze prawdziwy (`' OR '1'='1`) |
| `zapytanie_doklejone` | Doklejone polecenie po średniku |
| `drop_table` | DROP TABLE / DATABASE |
| `opoznienie` | Opóźnienie (SLEEP, WAITFOR) |
| `katalog_bazy` | Odczyt katalogu bazy (information_schema) |
| `procedura_systemowa` | Procedury systemowe (xp_cmdshell, INTO OUTFILE) |
| `komentarz_po_cudzyslowie`, `select_from`, `hex_lub_char` | Sygnały pomocnicze |

## Co trzeba zmienić we froncie (`admin_panel/frontend`)

- `src/api/backend/mappers.ts`, `ALERT_TYPE_FROM_BACKEND`: dodać `rosyjska_dezinformacja` i `sql_injection`. Dziś nieznane typy trafiają do `system` i dostają opis luki informacyjnej.
- `describeAlert`: jako opis użyć `details.opis`. Do metryk wstawić `count` (zapytania lub próby), `details.przypadek.url` (link), `details.wystapienia[0]` (ostatnie wystąpienie) i, dla SQL injection, `users` (źródła).
- `src/api/types.ts`: dodać oba typy do unii typów alertów oraz flagi `rosyjska_dezinformacja` i `sql_injection` do `CheckFlag`.
