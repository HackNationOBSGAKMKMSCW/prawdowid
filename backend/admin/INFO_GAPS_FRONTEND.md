# Luki informacyjne: API dla frontu panelu admina

Dokument opisuje, jak panel ma pokazać tematy, o które **często się pyta**, a system **nie ma na nie danych**. Wszystkie endpointy są w backendzie panelu (`uvicorn admin.api:create_app --factory --port 8100`, prefiks `/api/admin`).

## Jak to działa

1. Każde udane sprawdzenie trafia do rejestru zapytań. Sprawdzenia przychodzą ze strony (`GET /api/check`, kanał `web`) i z bota WhatsApp (kanał `whatsapp`).
2. Twierdzenia z zapytania są grupowane w **tematy**: podobne sformułowania trafiają do jednego tematu.
3. Twierdzenie **nie ma pokrycia w danych**, gdy jego werdykt to `brak_wystarczajacych_danych` albo `nieweryfikowalny`. Błąd analizy (`blad_analizy`) się nie liczy.
4. Backend liczy **zapytania bez pokrycia** o dany temat w oknie czasu (domyślnie 7 dni). Dwa twierdzenia z jednego zapytania liczą się raz.
5. Po przekroczeniu progu (domyślnie 3 zapytania) temat dostaje stan `aktywna` i powstaje alert `luka_informacyjna`. Admin widzi go w panelu.

Cykl stanów tematu (`gap_status`):

```
brak ──(1. zapytanie bez pokrycia)──► podejrzenie ──(próg)──► aktywna ──► w_uzupelnianiu ──► zamknieta
                                                                 └──────────────────────────► odrzucona
```

- `podejrzenie`: były zapytania bez pokrycia, ale poniżej progu. W panelu to sekcja „Obserwowane”.
- `aktywna`: luka. To sygnał dla admina.
- `w_uzupelnianiu`, `zamknieta`, `odrzucona`: decyzje admina, ustawiane przez `POST /info-gaps/{topic_id}`.
- Gdy o temat pojawi się rozstrzygnięcie ze źródłami (prawda albo fałsz), luka **zamyka się sama**, a alert dostaje stan `rozwiazany`.
- Po zamknięciu lub odrzuceniu licznik zaczyna się od nowa, od chwili decyzji.

Tryb liczenia ustawia `monitoring.info_gap_count_by`:
- `zapytania` (domyślnie): próg `info_gap_min_queries`.
- `osoby`: próg `info_gap_min_users`, czyli liczba różnych osób.

Strona nie ma logowania i wszyscy jej użytkownicy liczą się jako jedna osoba. W trybie `osoby` ruch ze strony praktycznie nie tworzy luk.

## Logowanie i uprawnienia

Każde żądanie wymaga nagłówka `Authorization: Bearer <token sesji>`. Token zwraca `POST /api/admin/auth/login`.

| Uprawnienie | Role | Do czego |
|---|---|---|
| `clusters:read` | moderator, analityk, admin | odczyt: `summary`, `ranking`, `info-gaps`, `topics/{id}` |
| `alerts:write` | moderator, analityk, admin | zmiana stanu luki i alertu |
| `settings:read` / `settings:write` | analityk (odczyt), admin | odczyt i zmiana progów (`/config`) |

Błędy mają kształt `{"detail": "komunikat po polsku"}`:

| Kod | Kiedy |
|---|---|
| 401 | brak tokenu, zły token albo wygasła sesja: przekieruj na logowanie |
| 403 | rola bez uprawnienia: ukryj akcję |
| 404 | nie ma tematu albo alertu |
| 422 | zły parametr, np. `hours=0` albo nieznany status |
| 503 | panel wyłączony (brak konfiguracji dostępu) |

## Endpointy

### `GET /api/admin/info-gaps/summary`: kafelki na górę strony

| Parametr | Domyślnie | Zakres | Znaczenie |
|---|---|---|---|
| `hours` | 168 | 1–8760 | okno statystyk |
| `top` | 5 | 0–50 | ile tematów w `top` |

```jsonc
{
  "generated_at": "2026-11-22T04:25:07.518Z",
  "window_hours": 168,
  "count_by": "zapytania",          // tryb liczenia: "zapytania" | "osoby"
  "threshold": 3,                   // próg luki w tym trybie
  "window_threshold_hours": 168,    // okno, w którym liczy się próg (monitoring.info_gap_window_hours)
  "uncovered_queries": 4,           // zapytania z co najmniej jednym twierdzeniem bez pokrycia
  "total_queries": 5,               // wszystkie zakończone zapytania w oknie
  "uncovered_share": 0.8,           // uncovered_queries / total_queries (0..1)
  "uncovered_topics": 2,            // tematy z co najmniej jednym zapytaniem bez pokrycia
  "by_status": {                    // liczba tematów w każdym stanie (cała historia, nie tylko okno)
    "podejrzenie": 1, "aktywna": 1, "w_uzupelnianiu": 0, "zamknieta": 0, "odrzucona": 0
  },
  "top": [ /* pozycje jak w ranking.items */ ]
}
```

### `GET /api/admin/info-gaps/ranking`: tabela „o co pytają, a nie mamy danych”

Zwraca tematy posortowane malejąco po liczbie zapytań bez pokrycia w oknie, **niezależnie od stanu**. Są w nim także tematy poniżej progu oraz zamknięte, o które znów pytano.

| Parametr | Domyślnie | Zakres | Znaczenie |
|---|---|---|---|
| `hours` | 168 | 1–2160 | okno (maks. 90 dni) |
| `min_queries` | 1 | ≥ 1 | pokaż tylko tematy z co najmniej N zapytaniami |
| `limit` | 50 | 1–500 | stronicowanie |
| `offset` | 0 | ≥ 0 | stronicowanie |

```jsonc
{
  "generated_at": "2026-11-22T04:25:07.526Z",
  "window_hours": 72,
  "count_by": "zapytania",
  "threshold": 3,
  "total": 2,                       // liczba wszystkich pozycji (do stronicowania)
  "limit": 50,
  "offset": 0,
  "items": [
    {
      "topic_id": "522a15a39b54",
      "label": "W Pcimiu Dolnym zamknięto wszystkie szkoły w listopadzie",
      "gap_status": "aktywna",      // brak | podejrzenie | aktywna | w_uzupelnianiu | zamknieta | odrzucona
      "gap_note": null,             // notatka admina
      "gap_since": "2026-11-22T04:25:07.112Z",
      "queries": 3,                 // zapytania bez pokrycia w oknie
      "users": 1,                   // różne osoby (strona = 1)
      "last_seen": "2026-11-22T04:25:07.112Z",
      "over_threshold": true,       // czy przekracza próg w bieżącym trybie
      "trend": [                    // dzień po dniu (UTC), od początku okna do dziś, także zera
        {"date": "2026-11-19", "queries": 0},
        {"date": "2026-11-20", "queries": 0},
        {"date": "2026-11-21", "queries": 0},
        {"date": "2026-11-22", "queries": 3}
      ]
    }
  ]
}
```

### `GET /api/admin/info-gaps`: lista luk według stanu

Ten endpoint już istniał. Doszło pole `gap_queries`.

| Parametr | Domyślnie | Znaczenie |
|---|---|---|
| `status` (powtarzalny) | `aktywna`, `w_uzupelnianiu` | np. `?status=podejrzenie&status=aktywna` |
| `limit`, `offset` | 100, 0 | stronicowanie |

```jsonc
{
  "items": [
    {
      "id": "522a15a39b54",
      "label": "W Pcimiu Dolnym zamknięto wszystkie szkoły w listopadzie",
      "created_at": "2026-11-22T04:25:07.107Z",
      "last_seen": "2026-11-22T04:25:07.112Z",
      "gap_status": "aktywna",
      "gap_since": "2026-11-22T04:25:07.112Z",
      "gap_users": 1,
      "gap_queries": 3,             // NOWE: zapytania bez pokrycia w oknie progu
      "gap_note": null,
      "gap_updated_at": "2026-11-22T04:25:07.112Z"
    }
  ]
}
```

Kolejność zależy od trybu: najpierw `gap_queries` (w trybie `osoby` najpierw `gap_users`), potem `last_seen`.

### `GET /api/admin/topics/{topic_id}`: szczegóły tematu (bez zmian)

Zwraca pola tematu, `tokens` (słowa kluczowe) i `claims`, czyli do 200 ostatnich twierdzeń z polami `query_id`, `ts`, `text`, `verdict`, `kind`, `sources_count`. Dochodzi `by_kind`, np. `{"luka": {"claims": 3, "users": 1}}`. To widok szuflady po kliknięciu wiersza.

### `POST /api/admin/info-gaps/{topic_id}`: decyzja admina (bez zmian)

```json
{"status": "w_uzupelnianiu", "note": "dodajemy źródło z gminy"}
```

- `status`: `aktywna`, `w_uzupelnianiu`, `zamknieta` albo `odrzucona`.
- `note` jest opcjonalne, do 1000 znaków.
- Odpowiedź to zaktualizowany temat, jak w `GET /topics/{id}`.
- `zamknieta` rozwiązuje alert, a `odrzucona` oznacza go jako fałszywy alarm.
- Wymaga uprawnienia `alerts:write`.

### Alerty: `GET /api/admin/alerts?type=luka_informacyjna`

Alert powstaje przy przejściu w stan `aktywna`:
- `subject` to `topic_id`, czyli link do `/topics/{subject}`;
- `count` to liczba zapytań bez pokrycia;
- `users` to liczba osób;
- `details.liczone_po` i `details.prog` mówią, według jakiej reguły alert powstał;
- `severity` ma wartość `wysoka`, gdy licznik przekracza 3-krotność progu, a w innym przypadku `srednia`.

Dashboard (`GET /api/admin/dashboard`) ma nowe pole `uncovered_queries` (w oknie `hours`). Pole `active_info_gaps` jest bez zmian.

### Progi: `GET` / `PATCH /api/admin/config`

`GET /config` w sekcji `monitoring` ma nowe pola:

```json
{
  "info_gap_count_by": "zapytania",
  "info_gap_min_queries": 3,
  "info_gap_min_users": 3,
  "info_gap_window_hours": 168
}
```

Zmiana działa od razu, bez restartu, i trafia do audytu:

```http
PATCH /api/admin/config
{"monitoring": {"info_gap_count_by": "zapytania", "info_gap_min_queries": 5}}
```

Walidacja:
- `info_gap_count_by` ∈ {`zapytania`, `osoby`};
- `info_gap_min_queries` 1–100 000;
- `info_gap_window_hours` 1–8760.

Zła wartość daje 422.

## Sugerowany widok strony „Luki informacyjne”

1. **Kafelki** z `summary`:
   - „Zapytania bez pokrycia”: `uncovered_queries` oraz `uncovered_share` w procentach;
   - „Aktywne luki”: `by_status.aktywna`;
   - „W uzupełnianiu”: `by_status.w_uzupelnianiu`;
   - „Obserwowane”: `by_status.podejrzenie`.
2. **Pasek reguły**, budowany z `count_by` i `threshold`:
   - tryb `zapytania`: „Luka = co najmniej {threshold} zapytań bez pokrycia w ciągu {window_threshold_hours} h”;
   - tryb `osoby`: „… {threshold} różnych osób …”.

   Obecny tekst w `GapsPage.tsx` zakłada zawsze osoby, więc trzeba go uzależnić od trybu.
3. **Tabela** z `ranking`:
   - kolumny: temat (`label`), liczba (`queries`), sparkline (`trend[].queries`), stan (`gap_status`), ostatnie (`last_seen`);
   - wiersze z `over_threshold: true` wyróżnione;
   - przełącznik okna 24 h / 7 dni / 30 dni (`hours`);
   - stronicowanie przez `total`, `limit` i `offset`.
4. **Kliknięcie wiersza** otwiera szczegóły (`GET /topics/{topic_id}`) z akcjami: „W uzupełnianiu”, „Zamknij”, „Odrzuć” (`POST /info-gaps/{topic_id}` z notatką). Po akcji przeładuj `summary` i `ranking`.
5. **Odświeżanie:** `summary` i `ranking` co 60 s, albo po powrocie do karty.

### Mapowanie na obecne typy frontu (`admin_panel/frontend`)

| Backend | `QueryCluster` / UI |
|---|---|
| `topic_id` / `id` | `id` |
| `label` | `label` |
| `queries` (ranking) / `gap_queries` (info-gaps) | `noEvidence` |
| `users` / `gap_users` | `uniqueSessions` |
| `gap_status` | `gapStatus` (`GAP_FROM_BACKEND`, bez zmian) |
| `trend[].queries` | dane do `Sparkline` (dziennie; dziś `hourly` liczone z twierdzeń jest godzinowe) |
| `over_threshold` | `isInformationGap` dla pozycji z rankingu |
| `last_seen`, `gap_since`, `gap_note` | `lastSeen`, `gapSince`, `gapNote` |

`MonitoringSettings` w `src/api/types.ts` trzeba rozszerzyć o `info_gap_count_by: 'zapytania' | 'osoby'` i `info_gap_min_queries: number`.

Wszystkie czasy są w UTC w formacie ISO 8601 (`...Z`). Daty w `trend` też są w UTC.
