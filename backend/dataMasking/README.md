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

Reguły są pisane pod naturalne wiadomości: małe litery, brak kropek w skrótach
(„ul Długa 15”), dowolne separatory w numerach („600.100.200”, „4405 1401 359”),
litera O zamiast zera („6OO 1OO 2OO”) i e-maile zapisane słownie.

| Typ                                                   | Jak rozpoznajemy                                                                                                                                              |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PESEL`, `NIP`, `REGON`, `NR_KONTA`, `KARTA`, `DOWOD` | wzorzec + **suma kontrolna**; słowo-klucz tuż przed wartością („pesel: …”) pomija walidację                                                                   |
| `TELEFON`                                             | `+48`/`0048`/`48`, komórkowe 9 cyfr od 4–8, stacjonarne; po „tel.”, „mój nr”, „zadzwoń” dowolny numer 7–12 cyfr                                               |
| `EMAIL`                                               | adres e-mail, także „jan małpa gmail kropka com”, „jan(at)gmail.com”, „[at] … [dot]”                                                                          |
| `PROFIL`                                              | `@nick` i link do profilu (facebook, fb, instagram, tiktok, x/twitter, linkedin, t.me…); linki do postów zostają                                              |
| `ADRES`                                               | `ul./ul/al./os./plac` + nazwa + numer; po „mieszkam/adres/zameldowany” także numer słownie; bez słowa-klucza „Długa 15/3”, „Długiej 15 m 3”, „przy Długiej 5” |
| `KOD_POCZTOWY`                                        | `00-000` przed nazwą miejscowości (też małą literą), „kod 80831”                                                                                              |
| `DATA_URODZENIA`                                      | data po „ur.”, „urodziłam się”, „urodziny”, „data urodzenia” (też „12 marca 85”); rok po „rocznik”                                                            |
| `NR_REJESTRACYJNY`                                    | po „nr rej.”, „tablice” albo tablica w stylu `WA12345` obok słów o aucie                                                                                      |
| `PASZPORT`, `IP`                                      | numer po słowie „paszport”; adres IP (bez „wersja 1.2.3.4”)                                                                                                   |

## Czego nie rusza (ochrona faktów)

- liczb z jednostką: „500 000 000 zł”, „600 100 200 osób”, „3,5%”, „230 głosami”,
- części większych liczb („4 500 000 000”) i odwołań prawnych: „poz. 1234”, „art. 15”, „Rozporządzenie 2016/679”,
- zwykłych dat i lat („15 października 2023”, „Tusk 15/03”, „urodził się w 1957 roku”),
- numerów alarmowych, wyników („2:1”), godzin, liczb bez poprawnej sumy kontrolnej i liczb w linkach,
- miast i dzielnic („mieszkam w Krakowie”, „na Mokotowie”).

## Znane luki

Numery telefonów słownie („sześćset sto dwieście”), adres bez numeru i bez słowa
„mieszkam” („pracuję na Długiej”), opisowe identyfikatory („moja szefowa z urzędu w X”)
oraz nazwisko zapisane tuż przed numerem mieszkania, jeśli kończy się jak ulica
(„Duda 15/3”).

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
