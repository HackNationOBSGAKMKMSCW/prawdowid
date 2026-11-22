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

Najpierw powstaje znormalizowana kopia tekstu (`normalize.py`), na której działają reguły;
znaczniki trafiają w oryginalne miejsca. Normalizacja usuwa niewidoczne znaki (zero-width,
miękki dywiz), zamienia cyfry pełnej szerokości i różne myślniki/spacje na zwykłe, literę O
w liczbie na zero („6OO 1OO 2OO”), liczby słownie dłuższe niż 6 cyfr na cyfry
(„sześćset sto dwieście”, „pięć jeden dwa…”) i rozdziela sklejone wiadomości
(„609 887 766Wnusiu”, „tel600100200”).

| Typ                                                   | Jak rozpoznajemy                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `PESEL`, `NIP`, `REGON`, `NR_KONTA`, `KARTA`, `DOWOD` | wzorzec + **suma kontrolna** (dowolne separatory); słowo-klucz tuż przed wartością („pesel: …”, „nr karty …”) pomija walidację                                                                                                                                                                                                                                                                                                                  |
| `TELEFON`                                             | `+48`/`0048`/`48`, komórkowe 9 cyfr od 4–8, stacjonarne, zagraniczne z `+`; po „tel.”, „mój nr”, „zadzwoń” dowolny numer 7–12 cyfr                                                                                                                                                                                                                                                                                                              |
| `EMAIL`                                               | adres e-mail, także „jan małpa gmail kropka com”, „jan(at)gmail.com”, „jan @ gmail . com”                                                                                                                                                                                                                                                                                                                                                       |
| `PROFIL`                                              | `@nick`, link do profilu, nick po nazwie serwisu („insta kasia_nowak”, „discord kasia#1234”); linki do postów zostają                                                                                                                                                                                                                                                                                                                           |
| `LOGIN`, `HASLO`                                      | hasło w kontekście logowania, także bez cyfr: „hasło: kotek”, „moje hasło to mruczek”, „hasło do poczty to Ala ma kota”, „hasło do wifi: …”, „hasło \"…\"”, „zmieniłam hasło na …”, „login / hasło”, „user X pass Y”, „klucz: …” (wifi); poza tym hasło z cyfrą lub znakiem specjalnym; PIN, PUK, CVV, BLIK, kod do domofonu/sejfu; login, nick. Slogany zostają („Hasło wyborcze PiS to…”, „Hasło akcji brzmi: …”, „Silne hasło to podstawa…”) |
| `IDENTYFIKATOR`                                       | numer klienta, umowy, polisy, paczki, legitymacji, albumu, prawa jazdy, VIN                                                                                                                                                                                                                                                                                                                                                                     |
| `ADRES`                                               | `ul./ul/al./os./plac` + nazwa + numer; po „mieszkam/adres/zameldowany” także numer słownie; bez słowa-klucza „Długa 15/3”, „Długiej 15 m 3”, „przy Długiej 5”, „na Kasprowicza 8” (bez „na Ukrainie 24 lutego”); sam numer mieszkania („m. 14”) przy słowach „klatka”, „piętro”, „u mnie”; zagraniczne „221B Baker Street”                                                                                                                      |
| `KOD_POCZTOWY`                                        | `00-000` przed albo po nazwie miejscowości, po numerze domu, „kod 80831”; brytyjski `NW1 6XE`                                                                                                                                                                                                                                                                                                                                                   |
| `LOKALIZACJA`                                         | współrzędne GPS, linki do map (Google, Apple, OSM, Waze), adres what3words                                                                                                                                                                                                                                                                                                                                                                      |
| `DATA_URODZENIA`                                      | data po „ur.”, „urodziłam się”, „urodziny”, „data urodzenia” (też „12 marca 85”, „w maju 1985”); rok po „ur.”, „urodzony w”, „rocznik”, „jestem z”                                                                                                                                                                                                                                                                                              |
| `NR_REJESTRACYJNY`                                    | po „nr rej.”, „tablice” albo tablica w stylu `WA12345` obok słów o aucie i marek („audi WGM 4521T”)                                                                                                                                                                                                                                                                                                                                             |
| `PASZPORT`, `IP`, `MAC`, `KSIEGA_WIECZYSTA`           | numer po słowie „paszport”; adres IP (bez „wersja 1.2.3.4”); adres MAC; `KR1P/00123456/7`                                                                                                                                                                                                                                                                                                                                                       |

### Wiek – tylko przy imieniu i nazwisku

Sam wiek nikogo nie wskazuje, więc jest maskowany (`WIEK`) tylko wtedy, gdy w tekście
jest imię i nazwisko (`names.py`: imię ze słownika w dowolnym przypadku i zdrobnieniu,
a po nim wyraz od wielkiej litery – „Jan Kowalski”, „z Kasią Nowak”).

- „Mam 67 lat, choruję na cukrzycę.” – zostaje,
- „Jan Kowalski ma 67 lat” → „Jan Kowalski ma [WIEK_1]”; także „Anna Nowak (45)”,
  „Krystyna Wiśniewska, 72 lata,”, „68-letni Jan Kowalski”, „68-latek”, „w wieku 45 lat”,
  „(lat 8)”, „mam 82 lata” (pierwsza osoba),
- trzecia osoba tylko, gdy w tym samym zdaniu przed nią stoi osoba („sąsiadka ma 80 lat”),
  a nie rzecz („ustawa ma 30 lat”, „Partia ma 30 lat”),
- liczby lat, które nie są wiekiem, zostają: „od 30 lat”, „30 lat temu”, „10-letni kredyt”,
  „30 lat tradycji”, „8 lat więzienia”.

## Czego nie rusza (ochrona faktów)

- liczb z jednostką: „500 000 000 zł”, „600 100 200 osób”, „3,5%”, „230 głosami”,
- części większych liczb („4 500 000 000”) i odwołań prawnych: „poz. 1234”, „art. 15”, „Rozporządzenie 2016/679”,
- zwykłych dat i lat („15 października 2023”, „Tusk 15/03”, „urodził się w 1957 roku”),
- numerów alarmowych, wyników („2:1”), godzin, liczb bez poprawnej sumy kontrolnej i liczb w linkach,
- miast i dzielnic („mieszkam w Krakowie”, „na Mokotowie”).

## Znane luki

Dane o zdrowiu („choruję na cukrzycę”) zostają, bo są
treścią sprawdzanych twierdzeń. Numery firm i infolinii są maskowane jak
prywatne (reguły ich nie odróżnią). Numery telefonów słownie („sześćset sto dwieście”), adres bez numeru i bez słowa
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

Odpowiedzi zawierają `rules_version` (skrót plików z regułami), widoczny w oknach we
frontendzie – po `git pull` od razu widać, czy backend działa na nowym kodzie.

Router jest podpięty pod serwer adaptera WhatsApp (port 8000). Samodzielnie
(z automatycznym przeładowaniem po zmianie reguł; `--no-reload` to wyłącza):

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
