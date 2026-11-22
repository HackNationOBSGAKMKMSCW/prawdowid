# Wyniki testów (sekcja 6 zadania)

Ten folder zawiera surowe wyniki i podsumowania ewaluacji. Każdy plik da się odtworzyć
komendami poniżej. Pliki mają w nazwie znacznik czasu przebiegu; starsze przebiegi zostają
dla porównania.

| Plik | Co zawiera |
|---|---|
| `werdykt_<czas>.md` / `.json` | warstwa werdyktu: 63 przypadki ze stałymi źródłami, mierniki, pełne wiersze |
| `cytaty_do_oceny_<czas>.csv` | losowa próba 20 cytatów do ręcznej oceny poprawności cytowania |
| `e2e_<etykieta>_<czas>.md` / `.json` | pełna ścieżka przez `GET /api/check` działającego backendu |
| `e2e_ruch_<czas>.md` / `.json` | test równoczesnych zapytań |

## Dwie warstwy pomiaru

1. **Warstwa werdyktu** (`analysis/scripts/eval_verdict.py`). Każdy przypadek z
   `analysis/data/eval/cases.json` ma własne, stałe źródła, więc wynik jest powtarzalny i nie
   zależy od internetu. Liczy:
   - macro-F1 na klasach obsługiwanych przez model (prawda, fałsz, brak wystarczających danych);
   - pokrycie cytowań;
   - wstrzymanie się;
   - odporność na prompt injection;
   - czas na przypadek i tokeny;
   - wynik per scenariusz A–J.
2. **Pełna ścieżka E2E** (`analysis/scripts/eval_e2e.py`). Zapytania z
   `analysis/data/eval/e2e_cases.json` (20 tekstów i 5 adresów URL) idą do działającego
   backendu: wyodrębnienie twierdzeń, wyszukiwanie, scraping i werdykt. Liczy:
   - medianę czasu od wejścia do odpowiedzi;
   - odsetek odpowiedzi bez błędu technicznego;
   - rozstrzygnięcia z cytatem i linkiem;
   - tokeny i liczbę wywołań modelu (z logu backendu po `X-Request-ID`);
   - czy próby injection zostały odnotowane.
   Wyniki zależą od dostępności źródeł w dniu pomiaru.

## Jak odtworzyć

```bash
cd analysis
.venv/Scripts/python -m scripts.eval_verdict                 # cały zestaw, ok. 10 min
.venv/Scripts/python -m scripts.eval_verdict C E             # wybrane scenariusze

# backend wg URUCHOMIENIE.md, potem:
.venv/Scripts/python -m scripts.eval_e2e --base http://127.0.0.1:8000
.venv/Scripts/python -m scripts.eval_e2e --base http://127.0.0.1:8000 --load 6
# scenariusz J: backend uruchomiony z pustym FREELLM_API_KEY albo z niedostępnym modelem
.venv/Scripts/python -m scripts.eval_e2e T01 T04 --expect-technical --label J --base ...
```

Model i endpoint czytane są z `.env` (`FREELLM_*`). Poprawność cytowań: w pliku
`cytaty_do_oceny_*.csv` wpisz w kolumnie `ocena` TAK (cytat wspiera tezę) albo NIE, potem:

```bash
.venv/Scripts/python -c "from pathlib import Path; from scripts.eval_metrics import citation_correctness as c; print(c(Path('../docs/wyniki-testow/cytaty_do_oceny_<czas>.csv')))"
```

## Warunki pomiaru

- Model: `gemma4:26b-a4b` przez Ollama (endpoint OpenAI-compatible), serwer w sieci prywatnej
  zespołu. Koszt API wynosi 0 zł; koszt to sprzęt i energia. Sprzęt serwera modelu: **do
  uzupełnienia przez zespół** (GPU, VRAM).
- Warstwa werdyktu działa z równoległością 3 (`VERDICT_CONCURRENCY`), więc czas na przypadek
  zawiera współdzielenie modelu przez 3 zapytania.
- Tokeny na 100 przypadków są liczone z odpowiedzi modelu (`usage`).

## Ograniczenia

- Etykiety referencyjne to 3 klasy modelu. API ma 5 werdyktów, ale dla pojedynczego
  twierdzenia osiągalne są tylko 3 (zob. `docs/AUDYT.md`, W5).
- Brak przypadków dla scenariuszy:
  - F (multimodalność): nie wdrożona;
  - G (spójność kanałów): WhatsApp jest w przebudowie;
  - H (pętla moderatora): sprawy moderatora nie istnieją w backendzie.
- Zestaw przypadków napisał zespół. Większość przypadków A–E powstała razem z promptem, a reguła
  R10 opisuje wprost przypadek E35/E36. Nowe przypadki E56–E63 (B i C) pisane są osobno, bez
  dopasowania do reguł. Wynik na zestawie ukrytym jury może być niższy.
- Poprawność cytowań wymaga ręcznej oceny próby.
