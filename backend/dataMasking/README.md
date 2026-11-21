# dataMasking – maskowanie danych osobowych

Usuwa z tekstu użytkownika dane osobowe **poza imieniem i nazwiskiem**. Działa bez LLM
i bez modeli ML: wzorce (regex), sumy kontrolne z biblioteki `python-stdnum` i słowa-klucze.

```python
from dataMasking import mask_personal_data

mask_personal_data("Anna Nowak, PESEL 44051401359, tel. 600 100 200").text
# 'Anna Nowak, PESEL [PESEL_1], tel. [TELEFON_1]'
```

Ta sama wartość dostaje zawsze ten sam znacznik (`[TELEFON_1]` dwa razy), a różne
wartości tego samego typu dostają kolejne numery. Znaczniki są nieodwracalne.

## Co jest maskowane

| Typ                                                   | Jak rozpoznajemy                                                                        |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `PESEL`, `NIP`, `REGON`, `NR_KONTA`, `KARTA`, `DOWOD` | wzorzec + **suma kontrolna**; słowo-klucz przed wartością („PESEL: …”) pomija walidację |
| `EMAIL`, `IP`                                         | wzorzec (IP z walidacją zakresu, bez „wersja 1.2.3.4”)                                  |
| `TELEFON`                                             | `+48`/`0048`, komórkowe 9 cyfr od 4–8, stacjonarne `(22) 123 45 67`                     |
| `ADRES`                                               | `ul.`/`al.`/`pl.`/`os.` + nazwa + numer, albo „mieszkam przy …”, „adres: …”             |
| `KOD_POCZTOWY`                                        | `00-000` przed nazwą miejscowości                                                       |
| `DATA_URODZENIA`                                      | data po „ur.”, „urodził się”, „data urodzenia”                                          |
| `PASZPORT`, `NR_REJESTRACYJNY`                        | wartość po słowie „paszport” / „nr rej.”, „tablice”                                     |

## Czego nie rusza (ochrona faktów)

- liczb z jednostką: „500 000 000 zł”, „600 100 200 osób”, „3,5%”,
- odwołań prawnych i przybliżeń: „poz. 1234”, „art. 212”, „druk nr …”, „około …”,
- zwykłych dat i lat („15 października 2023”, „urodził się w 1949 roku”),
- liczb bez poprawnej sumy kontrolnej i liczb w linkach.

## Znane luki

Adres bez słowa-klucza i bez numeru („mieszkam na Długiej w Gdańsku”), opisowe
identyfikatory („moja szefowa z urzędu w X”), nicki i linki do prywatnych profili.

## REST API

`POST /api/masking` z `{ "text": "…" }` zwraca:

```json
{
  "masked_text": "Anna Nowak, [EMAIL_1]",
  "entities": [{ "label": "EMAIL", "placeholder": "[EMAIL_1]", "start": 12, "end": 25 }],
  "counts": { "EMAIL": 1 }
}
```

Zamaskowane wartości nie są odsyłane: `start`/`end` wskazują je w tekście wysłanym przez klienta.

`POST /api/masking/llm-input` z `{ "text": "…" }` zwraca `{ llm_text, counts, warnings }`:
dokładnie ten tekst, który `InputSanitizer` wstawia do promptu LLM. Nic nie trafia do modelu.

## Gdzie działa przed LLM

`textAnalysis.analysis.InputSanitizer.sanitize` maskuje dane, zanim tekst trafi do promptu
(strona i WhatsApp). Liczba zamaskowanych wartości (bez samych wartości) trafia do logu;
nie jest dopisywana do `security_warnings`, bo te oznaczają próbę prompt injection.

Router jest podpięty pod serwer adaptera WhatsApp (port 8000). Samodzielnie:

```bash
cd backend && python -m dataMasking --port 8000
```

We frontendzie po kliknięciu **„Sprawdź”** pojawia się okno **„Do LLM trafi ten tekst”**
(domyślnie w `npm run dev`, w buildzie produkcyjnym z `VITE_SHOW_LLM_INPUT=true`).
Osobne okno testowe otwiera przycisk **„Test maskowania”** w pasku DEMO
(widoczny domyślnie w trybie `mock`, w trybie `live` po ustawieniu `VITE_DEMO_BAR=true`).
Okno zawsze pyta prawdziwy backend.

## Testy

```bash
python -m pytest backend/dataMasking
```

Przypadki są w `tests/cases.py`: `MASKED` (musi zniknąć) i `KEPT` (musi zostać).
Nowy błąd? Najpierw dopisz przypadek, potem poprawiaj reguły w `rules.py`.
