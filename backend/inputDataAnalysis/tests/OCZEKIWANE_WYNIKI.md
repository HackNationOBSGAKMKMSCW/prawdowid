# Oczekiwane wyniki testów modułu `inputDataAnalysis`

Plik generowany: `python -m inputDataAnalysis.tests.generuj_tabele` (z katalogu `backend/`).
Uruchomienie: `python -m pytest inputDataAnalysis/tests -v`. Przypadki `LV` wymagają `RUN_LLM_TESTS=1`.
Kolumna „Status”: ✅ oczekiwany wynik jest wymagany; ⚠️ znany błąd (test `xfail`, opis pod tabelą).

Łącznie przypadków: **411**.

## DT: TimeRef.from_iso: parsowanie dat ISO na przedziały (36)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| DT01 | pełna data dzienna | from_iso('2024-03-12') | 2024-03-12 … 2024-03-12, granularity=day | ✅ |
| DT02 | sam miesiąc | from_iso('2024-03') | 2024-03-01 … 2024-03-31, granularity=month | ✅ |
| DT03 | luty w roku przestępnym | from_iso('2024-02') | 2024-02-01 … 2024-02-29, granularity=month | ✅ |
| DT04 | luty w roku zwykłym | from_iso('2023-02') | 2023-02-01 … 2023-02-28, granularity=month | ✅ |
| DT05 | miesiąc 30-dniowy | from_iso('2024-04') | 2024-04-01 … 2024-04-30, granularity=month | ✅ |
| DT06 | sam rok | from_iso('2024') | 2024-01-01 … 2024-12-31, granularity=year | ✅ |
| DT07 | kwartał Q1 | from_iso('2024-Q1') | 2024-01-01 … 2024-03-31, granularity=quarter | ✅ |
| DT08 | kwartał małą literą | from_iso('2024-q4') | 2024-10-01 … 2024-12-31, granularity=quarter | ✅ |
| DT09 | kwartał bez myślnika | from_iso('2024Q2') | 2024-04-01 … 2024-06-30, granularity=quarter | ✅ |
| DT10 | kwartał Q3 | from_iso('2023-Q3') | 2023-07-01 … 2023-09-30, granularity=quarter | ✅ |
| DT11 | datetime z godziną | from_iso('2024-03-12T15:30:00') | 2024-03-12 … 2024-03-12, granularity=day | ✅ |
| DT12 | datetime ze strefą Z | from_iso('2024-03-12T00:00:00Z') | 2024-03-12 … 2024-03-12, granularity=day | ✅ |
| DT13 | spacje wokół daty | from_iso(' 2024-03-12 ') | 2024-03-12 … 2024-03-12, granularity=day | ✅ |
| DT14 | pusty napis | from_iso('') | None | ✅ |
| DT15 | same spacje | from_iso('   ') | None | ✅ |
| DT16 | tekst zamiast daty | from_iso('nie data') | None | ✅ |
| DT17 | miesiąc 13 | from_iso('2024-13') | None | ✅ |
| DT18 | 30 lutego | from_iso('2024-02-30') | None | ✅ |
| DT19 | 29 lutego w roku zwykłym | from_iso('2023-02-29') | None | ✅ |
| DT20 | 29 lutego w roku przestępnym | from_iso('2024-02-29') | 2024-02-29 … 2024-02-29, granularity=day | ✅ |
| DT21 | format polski DD.MM.RRRR nie jest ISO | from_iso('12.03.2024') | None | ✅ |
| DT22 | kwartał Q5 | from_iso('2024-Q5') | None | ✅ |
| DT23 | rok dwucyfrowy | from_iso('24') | None | ✅ |
| DT24 | przedział = pełny miesiąc → month | from_iso('2024-03-01', '2024-03-31') | 2024-03-01 … 2024-03-31, granularity=month | ✅ |
| DT25 | przedział = pełny rok → year | from_iso('2024-01-01', '2024-12-31') | 2024-01-01 … 2024-12-31, granularity=year | ✅ |
| DT26 | ten sam dzień jako przedział → day | from_iso('2024-03-12', '2024-03-12') | 2024-03-12 … 2024-03-12, granularity=day | ✅ |
| DT27 | tydzień bez podpowiedzi → range | from_iso('2024-03-10', '2024-03-16') | 2024-03-10 … 2024-03-16, granularity=range | ✅ |
| DT28 | tydzień z podpowiedzią week | from_iso('2024-03-10', '2024-03-16', 'week') | 2024-03-10 … 2024-03-16, granularity=week | ✅ |
| DT29 | kwartał jako przedział + podpowiedź quarter | from_iso('2024-01-01', '2024-03-31', 'quarter') | 2024-01-01 … 2024-03-31, granularity=quarter | ✅ |
| DT30 | od miesiąca do miesiąca | from_iso('2024-03', '2024-05') | 2024-03-01 … 2024-05-31, granularity=range | ✅ |
| DT31 | koniec przed początkiem jest ignorowany | from_iso('2024-03-20', '2024-03-10') | 2024-03-20 … 2024-03-20, granularity=day | ✅ |
| DT32 | nieczytelny koniec jest ignorowany | from_iso('2024-03-12', 'bzdura') | 2024-03-12 … 2024-03-12, granularity=day | ✅ |
| DT33 | rok do roku | from_iso('2024', '2025') | 2024-01-01 … 2025-12-31, granularity=range | ✅ |
| DT34 | podpowiedź month nie nadpisuje dnia | from_iso('2024-03-12', '', 'month') | 2024-03-12 … 2024-03-12, granularity=day | ✅ |
| DT35 | miesiąc + jego ostatni dzień → month | from_iso('2024-01', '2024-01-31') | 2024-01-01 … 2024-01-31, granularity=month | ✅ |
| DT36 | pusty początek, podany koniec | from_iso('', '2024-03-12') | None | ✅ |

## DW: TimeRef.width_days: szerokość przedziału (8)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| DW01 | szerokość 2024-03-12 | from_iso('2024-03-12').width_days | 1 | ✅ |
| DW02 | szerokość 2024-03 | from_iso('2024-03').width_days | 31 | ✅ |
| DW03 | szerokość 2024-02 | from_iso('2024-02').width_days | 29 | ✅ |
| DW04 | szerokość 2023-02 | from_iso('2023-02').width_days | 28 | ✅ |
| DW05 | szerokość 2024 | from_iso('2024').width_days | 366 | ✅ |
| DW06 | szerokość 2023 | from_iso('2023').width_days | 365 | ✅ |
| DW07 | szerokość 2024-Q1 | from_iso('2024-Q1').width_days | 91 | ✅ |
| DW08 | szerokość 2023-Q1 | from_iso('2023-Q1').width_days | 90 | ✅ |

## DI: dist(): odległość między przedziałami (15)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| DI01 | dzień w środku miesiąca | dist(2024-03 (miesiąc), 2024-03-15) | 0 (symetrycznie) | ✅ |
| DI02 | ten sam dzień | dist(2024-03-12, 2024-03-12) | 0 (symetrycznie) | ✅ |
| DI03 | dni sąsiednie | dist(2024-03-12, 2024-03-13) | 1 (symetrycznie) | ✅ |
| DI04 | miesiąc i dzień po nim | dist(2024-03 (miesiąc), 2024-04-02) | 2 (symetrycznie) | ✅ |
| DI05 | dwa lata | dist(2022-03-12, 2024-03-12) | 731 (symetrycznie) | ✅ |
| DI06 | sąsiednie lata | dist(2023 (rok), 2024 (rok)) | 1 (symetrycznie) | ✅ |
| DI07 | lata 2020 i 2024 | dist(2020 (rok), 2024 (rok)) | 1096 (symetrycznie) | ✅ |
| DI08 | miesiąc w roku | dist(2024 (rok), 2024-07 (miesiąc)) | 0 (symetrycznie) | ✅ |
| DI09 | kwartał i dzień po nim | dist(2024-Q1 (kwartał), 2024-04-01) | 1 (symetrycznie) | ✅ |
| DI10 | przez 29 lutego | dist(2024-02-28, 2024-03-01) | 2 (symetrycznie) | ✅ |
| DI11 | bez 29 lutego | dist(2023-02-28, 2023-03-01) | 1 (symetrycznie) | ✅ |
| DI12 | przedział tygodniowy i dzień | dist(2024-03-10…2024-03-16 (range), 2024-03-20) | 4 (symetrycznie) | ✅ |
| DI13 | przełom roku | dist(2024-12-31, 2025-01-01) | 1 (symetrycznie) | ✅ |
| DI14 | nakładające się przedziały | dist(2024-03-01…2024-05-31 (range), 2024-04-01…2024-06-30 (range)) | 0 (symetrycznie) | ✅ |
| DI15 | przedział zawarty w przedziale | dist(2024 (rok), 2024-Q2 (kwartał)) | 0 (symetrycznie) | ✅ |

## RE: parse_relative(): wyrażenia względne (baza 2024-03-20, środa) (28)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| RE01 | „wczoraj” | parse_relative('wczoraj', 2024-03-20) | 2024-03-19 … 2024-03-19, day | ✅ |
| RE02 | „dzisiaj” | parse_relative('dzisiaj', 2024-03-20) | 2024-03-20 … 2024-03-20, day | ✅ |
| RE03 | „dziś” | parse_relative('dziś', 2024-03-20) | 2024-03-20 … 2024-03-20, day | ✅ |
| RE04 | „przedwczoraj” | parse_relative('przedwczoraj', 2024-03-20) | 2024-03-18 … 2024-03-18, day | ✅ |
| RE05 | „jutro” | parse_relative('jutro', 2024-03-20) | 2024-03-21 … 2024-03-21, day | ✅ |
| RE06 | „pojutrze” | parse_relative('pojutrze', 2024-03-20) | 2024-03-22 … 2024-03-22, day | ✅ |
| RE07 | „2 dni temu” | parse_relative('2 dni temu', 2024-03-20) | 2024-03-18 … 2024-03-18, day | ✅ |
| RE08 | „5 dni temu” | parse_relative('5 dni temu', 2024-03-20) | 2024-03-15 … 2024-03-15, day | ✅ |
| RE09 | „tydzień temu” | parse_relative('tydzień temu', 2024-03-20) | 2024-03-10 … 2024-03-16, week | ✅ |
| RE10 | „2 tygodnie temu” | parse_relative('2 tygodnie temu', 2024-03-20) | 2024-03-03 … 2024-03-09, week | ✅ |
| RE11 | „w zeszłym tygodniu” | parse_relative('w zeszłym tygodniu', 2024-03-20) | 2024-03-10 … 2024-03-16, week | ✅ |
| RE12 | „tydzień” | parse_relative('tydzień', 2024-03-20) | 2024-03-10 … 2024-03-16, week | ✅ |
| RE13 | „miesiąc temu” | parse_relative('miesiąc temu', 2024-03-20) | 2024-02-01 … 2024-02-29, month | ✅ |
| RE14 | „3 miesiące temu” | parse_relative('3 miesiące temu', 2024-03-20) | 2023-12-01 … 2023-12-31, month | ✅ |
| RE15 | „miesiąc” | parse_relative('miesiąc', 2024-03-20) | 2024-02-01 … 2024-02-29, month | ✅ |
| RE16 | „rok temu” | parse_relative('rok temu', 2024-03-20) | 2023-01-01 … 2023-12-31, year | ✅ |
| RE17 | „w zeszłym roku” | parse_relative('w zeszłym roku', 2024-03-20) | 2023-01-01 … 2023-12-31, year | ✅ |
| RE18 | „2 lata temu” | parse_relative('2 lata temu', 2024-03-20) | 2022-01-01 … 2022-12-31, year | ✅ |
| RE19 | „10 lat temu” | parse_relative('10 lat temu', 2024-03-20) | 2014-01-01 … 2014-12-31, year | ✅ |
| RE20 | „rok” | parse_relative('rok', 2024-03-20) | 2023-01-01 … 2023-12-31, year | ✅ |
| RE21 | „w poniedziałek” | parse_relative('w poniedziałek', 2024-03-20) | 2024-03-18 … 2024-03-18, day | ✅ |
| RE22 | „wczoraj” | parse_relative('wczoraj', 2024-03-01) | 2024-02-29 … 2024-02-29, day | ✅ |
| RE23 | „wczoraj” | parse_relative('wczoraj', 2025-01-01) | 2024-12-31 … 2024-12-31, day | ✅ |
| RE24 | „” | parse_relative('', 2024-03-20) | None | ✅ |
| RE25 | „   ” | parse_relative('   ', 2024-03-20) | None | ✅ |
| RE26 | „niedawno” | parse_relative('niedawno', 2024-03-20) | None | ✅ |
| RE27 | „sdfsdf” | parse_relative('sdfsdf', 2024-03-20) | None | ✅ |
| RE28 | „godzinę temu” | parse_relative('godzinę temu', 2024-03-20) | 2024-03-20 … 2024-03-20, day | ⚠️ |

Znane błędy:
- **RE28**: dateparser nie rozpoznaje biernika „godzinę temu” i zwraca None

## WD: parse_weekday(): polskie nazwy dni tygodnia (27)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| WD01 | 'poniedziałek' | parse_weekday('poniedziałek') | 0 (pon) | ✅ |
| WD02 | 'w poniedziałek' | parse_weekday('w poniedziałek') | 0 (pon) | ✅ |
| WD03 | 'pon.' | parse_weekday('pon.') | 0 (pon) | ✅ |
| WD04 | 'wtorek' | parse_weekday('wtorek') | 1 (wt) | ✅ |
| WD05 | 'we wtorek' | parse_weekday('we wtorek') | 1 (wt) | ✅ |
| WD06 | 'wt' | parse_weekday('wt') | 1 (wt) | ✅ |
| WD07 | 'środa' | parse_weekday('środa') | 2 (śr) | ✅ |
| WD08 | 'ŚRODA' | parse_weekday('ŚRODA') | 2 (śr) | ✅ |
| WD09 | 'w środę' | parse_weekday('w środę') | 2 (śr) | ✅ |
| WD10 | 'śr.' | parse_weekday('śr.') | 2 (śr) | ✅ |
| WD11 | 'czwartek' | parse_weekday('czwartek') | 3 (czw) | ✅ |
| WD12 | 'czw.' | parse_weekday('czw.') | 3 (czw) | ✅ |
| WD13 | 'piątek' | parse_weekday('piątek') | 4 (pt) | ✅ |
| WD14 | 'w piątek' | parse_weekday('w piątek') | 4 (pt) | ✅ |
| WD15 | 'pt' | parse_weekday('pt') | 4 (pt) | ✅ |
| WD16 | 'sobota' | parse_weekday('sobota') | 5 (sob) | ✅ |
| WD17 | 'w sobotę' | parse_weekday('w sobotę') | 5 (sob) | ✅ |
| WD18 | 'sob.' | parse_weekday('sob.') | 5 (sob) | ✅ |
| WD19 | 'niedziela' | parse_weekday('niedziela') | 6 (nd) | ✅ |
| WD20 | 'w niedzielę' | parse_weekday('w niedzielę') | 6 (nd) | ✅ |
| WD21 | 'nd' | parse_weekday('nd') | 6 (nd) | ✅ |
| WD22 | 'Dziś w środę 12 marca' | parse_weekday('Dziś w środę 12 marca') | 2 (śr) | ✅ |
| WD23 | 'wtedy' | parse_weekday('wtedy') | None | ✅ |
| WD24 | 'środowy' | parse_weekday('środowy') | None | ✅ |
| WD25 | '' | parse_weekday('') | None | ✅ |
| WD26 | None | parse_weekday(None) | None | ✅ |
| WD27 | '12 marca 2024' | parse_weekday('12 marca 2024') | None | ✅ |

## FM: Formatowanie dat i liczebników po polsku (54)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| FM01 | fmt_day(2024-03-12) | fmt_day(2024-03-12) | „12 marca 2024” | ✅ |
| FM02 | fmt_day(2025-01-01) | fmt_day(2025-01-01) | „1 stycznia 2025” | ✅ |
| FM03 | fmt_on – 2024-03-12 | fmt_on(2024-03-12) | „na 12 marca 2024” | ✅ |
| FM04 | fmt_on – 2024-03 (miesiąc) | fmt_on(2024-03 (miesiąc)) | „na marzec 2024” | ✅ |
| FM05 | fmt_on – 2023-12 (miesiąc) | fmt_on(2023-12 (miesiąc)) | „na grudzień 2023” | ✅ |
| FM06 | fmt_on – 2015 (rok) | fmt_on(2015 (rok)) | „na 2015 r.” | ✅ |
| FM07 | fmt_on – 2024-Q2 (kwartał) | fmt_on(2024-Q2 (kwartał)) | „na 2. kwartał 2024 r.” | ✅ |
| FM08 | fmt_on – 2024-03-10…2024-03-16 (range) | fmt_on(2024-03-10…2024-03-16 (range)) | „na okres 10–16 marca 2024” | ✅ |
| FM09 | fmt_on – 2024-02-28…2024-03-05 (range) | fmt_on(2024-02-28…2024-03-05 (range)) | „na okres 28 lutego 2024 – 5 marca 2024” | ✅ |
| FM10 | fmt_on – 2024-03-10…2024-03-16 (week) | fmt_on(2024-03-10…2024-03-16 (week)) | „na okres 10–16 marca 2024” | ✅ |
| FM11 | fmt_at – 2024-03-12 | fmt_at(2024-03-12) | „12 marca 2024” | ✅ |
| FM12 | fmt_at – 2024-03 (miesiąc) | fmt_at(2024-03 (miesiąc)) | „w marcu 2024” | ✅ |
| FM13 | fmt_at – 2024-02 (miesiąc) | fmt_at(2024-02 (miesiąc)) | „w lutym 2024” | ✅ |
| FM14 | fmt_at – 2024-11 (miesiąc) | fmt_at(2024-11 (miesiąc)) | „w listopadzie 2024” | ✅ |
| FM15 | fmt_at – 2015 (rok) | fmt_at(2015 (rok)) | „w 2015 r.” | ✅ |
| FM16 | fmt_at – 2024-Q2 (kwartał) | fmt_at(2024-Q2 (kwartał)) | „w 2. kwartale 2024 r.” | ✅ |
| FM17 | fmt_at – 2024-03-10…2024-03-16 (range) | fmt_at(2024-03-10…2024-03-16 (range)) | „w okresie 10–16 marca 2024” | ✅ |
| FM18 | fmt_from – 2024-03-12 | fmt_from(2024-03-12) | „z 12 marca 2024” | ✅ |
| FM19 | fmt_from – 2023-12 (miesiąc) | fmt_from(2023-12 (miesiąc)) | „z grudnia 2023” | ✅ |
| FM20 | fmt_from – 2015 (rok) | fmt_from(2015 (rok)) | „z 2015 r.” | ✅ |
| FM21 | fmt_from – 2024-Q2 (kwartał) | fmt_from(2024-Q2 (kwartał)) | „z 2. kwartału 2024 r.” | ✅ |
| FM22 | fmt_from – 2024-03-10…2024-03-16 (range) | fmt_from(2024-03-10…2024-03-16 (range)) | „z okresu 10–16 marca 2024” | ✅ |
| FM23 | fmt_from – 2025-01-01 | fmt_from(2025-01-01) | „z 1 stycznia 2025” | ✅ |
| FM24 | fmt_days(1) | fmt_days(1) | „1 dzień” | ✅ |
| FM25 | fmt_days(2) | fmt_days(2) | „2 dni” | ✅ |
| FM26 | fmt_days(5) | fmt_days(5) | „5 dni” | ✅ |
| FM27 | fmt_days(731) | fmt_days(731) | „731 dni” | ✅ |
| FM28 | plural(1, rok/lata/lat) | plural(1, rok/lata/lat) | „1 rok” | ✅ |
| FM29 | plural(2, rok/lata/lat) | plural(2, rok/lata/lat) | „2 lata” | ✅ |
| FM30 | plural(4, rok/lata/lat) | plural(4, rok/lata/lat) | „4 lata” | ✅ |
| FM31 | plural(5, rok/lata/lat) | plural(5, rok/lata/lat) | „5 lat” | ✅ |
| FM32 | plural(12, rok/lata/lat) | plural(12, rok/lata/lat) | „12 lat” | ✅ |
| FM33 | plural(13, rok/lata/lat) | plural(13, rok/lata/lat) | „13 lat” | ✅ |
| FM34 | plural(14, rok/lata/lat) | plural(14, rok/lata/lat) | „14 lat” | ✅ |
| FM35 | plural(21, rok/lata/lat) | plural(21, rok/lata/lat) | „21 lat” | ✅ |
| FM36 | plural(22, rok/lata/lat) | plural(22, rok/lata/lat) | „22 lata” | ✅ |
| FM37 | plural(25, rok/lata/lat) | plural(25, rok/lata/lat) | „25 lat” | ✅ |
| FM38 | plural(104, rok/lata/lat) | plural(104, rok/lata/lat) | „104 lata” | ✅ |
| FM39 | plural(112, rok/lata/lat) | plural(112, rok/lata/lat) | „112 lat” | ✅ |
| FM40 | plural(2, miesiąc/…) | plural(2, miesiąc/…) | „2 miesiące” | ✅ |
| FM41 | plural(5, miesiąc/…) | plural(5, miesiąc/…) | „5 miesięcy” | ✅ |
| FM42 | plural(22, miesiąc/…) | plural(22, miesiąc/…) | „22 miesiące” | ✅ |
| FM43 | humanize_days(0) | humanize_days(0) | „0 dni” | ✅ |
| FM44 | humanize_days(1) | humanize_days(1) | „1 dzień” | ✅ |
| FM45 | humanize_days(59) | humanize_days(59) | „59 dni” | ✅ |
| FM46 | humanize_days(60) | humanize_days(60) | „2 miesiące” | ✅ |
| FM47 | humanize_days(89) | humanize_days(89) | „2 miesiące” | ✅ |
| FM48 | humanize_days(150) | humanize_days(150) | „5 miesięcy” | ✅ |
| FM49 | humanize_days(364) | humanize_days(364) | „12 miesięcy” | ✅ |
| FM50 | humanize_days(365) | humanize_days(365) | „1 rok” | ✅ |
| FM51 | humanize_days(730) | humanize_days(730) | „2 lata” | ✅ |
| FM52 | humanize_days(1461) | humanize_days(1461) | „4 lata” | ✅ |
| FM53 | humanize_days(1744) | humanize_days(1744) | „4 lata” | ✅ |
| FM54 | humanize_days(1826) | humanize_days(1826) | „5 lat” | ✅ |

## SP: locate_quote(): odnajdywanie cytatów w tekście (22)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| SP01 | dokładnie, początek tekstu | quote='Rząd przyjął' | „Rząd przyjął” od pozycji 0 | ✅ |
| SP02 | dokładnie, środek tekstu | quote='skandaliczna zdrada' | „skandaliczna zdrada” od pozycji 24 | ✅ |
| SP03 | dokładnie, koniec tekstu | quote='w całości.' | „w całości.” od pozycji 91 | ✅ |
| SP04 | powtórzony cytat + start_hint | quote='Rząd przyjął', start_hint=5 | „Rząd przyjął” od pozycji 65 | ✅ |
| SP05 | start_hint za ostatnim wystąpieniem → pierwsze | quote='Rząd przyjął', start_hint=90 | „Rząd przyjął” od pozycji 0 | ✅ |
| SP06 | wielkie litery | quote='RZĄD PRZYJĄŁ USTAWĘ' | „Rząd przyjął ustawę” od pozycji 0 | ✅ |
| SP07 | małe litery + start_hint | quote='rząd przyjął', start_hint=5 | „Rząd przyjął” od pozycji 65 | ✅ |
| SP08 | proste cudzysłowy zamiast „” | quote='zdrada "elit"' | „zdrada „elit”” | ✅ |
| SP09 | cudzysłów francuski | quote='zdrada «elit»' | „zdrada „elit”” | ✅ |
| SP10 | dywiz zamiast półpauzy | quote='budżet - w całości' | „budżet – w całości” | ✅ |
| SP11 | spacje wokół cytatu | quote='  skandaliczna  ' | „skandaliczna” od pozycji 24 | ✅ |
| SP12 | fuzzy: jedna literówka | quote='To skandaliczna zdrdda „elit” wobec narodu' | „To skandaliczna zdrada „elit” wobec narodu” | ✅ |
| SP13 | fuzzy: brak cudzysłowów wokół słowa | quote='skandaliczna zdrada elit wobec narodu' | „skandaliczna zdrada „elit” wobec narodu” | ⚠️ |
| SP14 | krótki cytat z literówką (< 8 znaków) | quote='zdrda' | None (odrzucony) | ✅ |
| SP15 | zmyślony cytat | quote='minister ukradł miliardy złotych' | None (odrzucony) | ✅ |
| SP16 | pusty cytat | quote='' | None (odrzucony) | ✅ |
| SP17 | cytat z samych spacji | quote='   ' | None (odrzucony) | ✅ |
| SP18 | pusty tekst | text='', quote='Rząd przyjął' | None (odrzucony) | ✅ |
| SP19 | cytat z dopisanym zmyślonym zdaniem | quote='To skandaliczna zdrada „elit” wobec narodu! Rząd przyjął też budżet – w całości. I jeszcze więcej tekstu którego nie ma' | None (odrzucony) | ⚠️ |
| SP20 | słowa w innej kolejności | quote='narodu wobec elit zdrada skandaliczna' | None (odrzucony) | ✅ |
| SP21 | cytat w polu z polskimi znakami | quote='zdrada „elit” wobec narodu!' | „zdrada „elit” wobec narodu!” | ✅ |
| SP22 | cytat = cały tekst | quote='Rząd przyjął ustawę. To skandaliczna zdrada „elit” wobec narodu! Rząd przyjął też budżet – w całości.' | „Rząd przyjął ustawę. To skandaliczna zdrada „elit” wobec narodu! Rząd przyjął też budżet – w całości.” od pozycji 0 | ✅ |

Znane błędy:
- **SP13**: zakres z partial_ratio_alignment ucina pierwszą i ostatnią literę („kandaliczna … narod”); brak dociągania do granic słów
- **SP19**: cytat dłuższy niż tekst jest „odnajdywany” jako cały tekst, bo partial_ratio dopasowuje krótszy napis (tekst) do dłuższego (cytatu)

## TS: TruthSource: adapter źródeł prawdy (14)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| TS01 | minimalne źródło | {'id': 's1', 'content': 'abc'} | id=s1, content=abc, published_at=None, label=s1 | ✅ |
| TS02 | aliasy source_id + text | {'source_id': 's2', 'text': 'abc'} | id=s2, content=abc | ✅ |
| TS03 | id liczbowe + body | {'id': 7, 'body': 'abc'} | id=7, content=abc | ✅ |
| TS04 | data ISO | {'id': 's', 'content': 'x', 'published_at': '2024-03-12'} | published_at=2024-03-12 | ✅ |
| TS05 | datetime ze strefą Z | {'id': 's', 'content': 'x', 'published_at': '2024-03-12T10:00:00Z'} | published_at=2024-03-12 | ✅ |
| TS06 | datetime z przesunięciem +02:00 | {'id': 's', 'content': 'x', 'published_at': '2024-03-12T23:30:00+02:00'} | published_at=2024-03-12 | ✅ |
| TS07 | obiekt datetime | {'id': 's', 'content': 'x', 'published_at': datetime.datetime(2024, 3, 12, 15, 0)} | published_at=2024-03-12 | ✅ |
| TS08 | alias date | {'id': 's', 'content': 'x', 'date': '2024-01-05'} | published_at=2024-01-05 | ✅ |
| TS09 | alias publication_date | {'id': 's', 'content': 'x', 'publication_date': '2024-01-06'} | published_at=2024-01-06 | ✅ |
| TS10 | tytuł jako etykieta | {'id': 's', 'content': 'x', 'title': 'PAP'} | label=PAP | ✅ |
| TS11 | url zachowany | {'id': 's', 'content': 'x', 'url': 'https://example.org/a'} | url=https://example.org/a | ✅ |
| TS12 | brak treści | {'id': 's'} | ValidationError | ✅ |
| TS13 | brak id | {'content': 'x'} | ValidationError | ✅ |
| TS14 | nieczytelna data | {'id': 's', 'content': 'x', 'published_at': 'nie-data-wcale'} | ValidationError | ✅ |

## RU: Reguły dat: evaluate() na gotowych obiektach (99)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| RU01 | DATE_MISMATCH: 2 lata różnicy | tekst 2024-03-12, źródło »PAP« 2022-03-12 [t_A=brak] | DATE_MISMATCH (high, Δ=731 dni); opis: „Tekst datuje »zawalenie mostu« na 12 marca 2024, a źródło »PAP« na 12 marca 2022 (różnica 731 dni).” | ✅ |
| RU02 | DATE_MISMATCH: 2 dni → średnia | tekst 2024-03-12, źródło 2024-03-14 [t_A=brak] | DATE_MISMATCH (medium, Δ=2 dni) | ✅ |
| RU03 | tolerancja +1 dzień | tekst 2024-03-12, źródło 2024-03-13 [t_A=brak] | brak problemów | ✅ |
| RU04 | tolerancja −1 dzień | tekst 2024-03-12, źródło 2024-03-11 [t_A=brak] | brak problemów | ✅ |
| RU05 | granica 30 dni → nadal średnia | tekst 2024-03-01, źródło 2024-03-31 [t_A=brak] | DATE_MISMATCH (medium, Δ=30 dni) | ✅ |
| RU06 | 31 dni → wysoka | tekst 2024-03-01, źródło 2024-04-01 [t_A=brak] | DATE_MISMATCH (high, Δ=31 dni) | ✅ |
| RU07 | „marzec 2024” vs 15.03.2024 → zgodne | tekst 2024-03 (miesiąc), źródło 2024-03-15 [t_A=brak] | brak problemów | ✅ |
| RU08 | miesiąc vs dzień poza nim | tekst 2024-03 (miesiąc), źródło 2024-04-02 [t_A=brak] | DATE_MISMATCH (medium, Δ=2 dni); opis: „Tekst datuje »zawalenie mostu« na marzec 2024, a źródło »PAP« na 2 kwietnia 2024 (różnica 2 dni).” | ✅ |
| RU09 | rok vs dzień tuż przed nim (w tolerancji) | tekst 2024 (rok), źródło 2023-12-31 [t_A=brak] | brak problemów | ✅ |
| RU10 | rok vs rok | tekst 2019 (rok), źródło 2021 (rok) [t_A=brak] | DATE_MISMATCH (high, Δ=367 dni); opis zawiera „na 2019 r., a źródło »PAP« na 2021 r.” | ✅ |
| RU11 | rola publication nie jest porównywana | role=publication, tekst 2024-03-12, źródło 2022-03-12 [t_A=brak] | brak problemów | ✅ |
| RU12 | źródło bez daty zdarzenia | tekst 2024-03-12, źródło: brak daty [t_A=brak] | brak problemów | ✅ |
| RU13 | tekst bez daty zdarzenia | tekst: brak daty, źródło 2022-03-12 [t_A=brak] | brak problemów | ✅ |
| RU14 | źródło bez tytułu → w opisie id | źródło id=kgp bez tytułu, tekst 2024-03-12, źródło 2022-03-12 [t_A=brak] | DATE_MISMATCH (high, Δ=731 dni); opis zawiera „a źródło »kgp«” | ✅ |
| RU15 | breaking: 4 dni > 3 dni | bieżące (recency 0.9), źródło 2024-03-08 [t_A=2024-03-12, kategoria=breaking] | OUTDATED_AS_CURRENT (high, Δ=4 dni); opis: „Tekst przedstawia »zawalenie mostu« jako bieżące, choć według źródła »Agencja« wydarzyło się 4 dni przed publikacją tekstu.” | ✅ |
| RU16 | breaking: dokładnie 3 dni → OK | bieżące, źródło 2024-03-09 [t_A=2024-03-12, kategoria=breaking] | brak problemów | ✅ |
| RU17 | polityczne: 31 dni > 30 | bieżące, źródło 2024-02-10 [t_A=2024-03-12, kategoria=political_legal] | OUTDATED_AS_CURRENT (high, Δ=31 dni) | ✅ |
| RU18 | polityczne: dokładnie 30 dni → OK | bieżące, źródło 2024-02-11 [t_A=2024-03-12, kategoria=political_legal] | brak problemów | ✅ |
| RU19 | gospodarcze: 367 dni > 365 | bieżące, źródło 2023-03-11 [t_A=2024-03-12, kategoria=economic] | OUTDATED_AS_CURRENT (high, Δ=367 dni); opis zawiera „1 rok przed publikacją” | ✅ |
| RU20 | gospodarcze: 193 dni → OK | bieżące, źródło 2023-09-01 [t_A=2024-03-12, kategoria=economic] | brak problemów | ✅ |
| RU21 | kategoria other: próg 30 dni | bieżące, źródło 2024-02-10 [t_A=2024-03-12] | OUTDATED_AS_CURRENT (high, Δ=31 dni) | ✅ |
| RU22 | nieznana kategoria → próg jak other | bieżące, źródło 2024-02-10 [t_A=2024-03-12, kategoria=sport] | OUTDATED_AS_CURRENT (high, Δ=31 dni) | ✅ |
| RU23 | recency 0.59 < 0.6 → OK | recency 0.59, źródło 2019-06-03 [t_A=2024-03-12, kategoria=breaking] | brak problemów | ✅ |
| RU24 | recency dokładnie 0.6 → flaga | recency 0.6, źródło 2019-06-03 [t_A=2024-03-12, kategoria=breaking] | OUTDATED_AS_CURRENT (high, Δ=1744 dni); opis: „Tekst przedstawia »zawalenie mostu« jako bieżące, choć według źródła »PAP« wydarzyło się 4 lata przed publikacją tekstu.” | ✅ |
| RU25 | zdarzenie zapowiadane (tense=future) | tense=future, źródło 2019-06-03 [t_A=2024-03-12, kategoria=breaking] | brak problemów | ✅ |
| RU26 | rola reference | role=reference, źródło 2019-06-03 [t_A=2024-03-12, kategoria=breaking] | brak problemów | ✅ |
| RU27 | źródło: plan, nie zdarzenie | status=planned, tense=present, źródło 2019-06-03 [t_A=2024-03-12, kategoria=breaking] | brak problemów | ✅ |
| RU28 | brak daty zdarzenia → data publikacji źródła | źródło bez daty zdarzenia, status=occurred, published_at 2019-06-04 [t_A=2024-03-12, kategoria=breaking] | OUTDATED_AS_CURRENT (high, Δ=1743 dni) | ✅ |
| RU29 | brak daty zdarzenia i status unknown | źródło bez daty zdarzenia, status=unknown [t_A=2024-03-12, kategoria=breaking] | brak problemów | ✅ |
| RU30 | data miesięczna: liczy się koniec miesiąca | bieżące, źródło 2024-02 (miesiąc) [t_A=2024-03-12, kategoria=breaking] | OUTDATED_AS_CURRENT (high, Δ=12 dni); opis zawiera „12 dni przed publikacją” | ✅ |
| RU31 | zdarzenie po dacie tekstu ≠ nieaktualne | bieżące, źródło 2024-03-12 (ten sam dzień) [t_A=2024-03-12, kategoria=breaking] | brak problemów | ✅ |
| RU32 | ANACHRONISM: zdarzenie 90 dni po tekście | przeszłe, źródło »Raport« 2024-05-30 [t_A=2024-03-01] | ANACHRONISM (high, Δ=90 dni); opis: „Tekst z 1 marca 2024 opisuje »zawalenie mostu«, które według źródła »Raport« nastąpiło dopiero 30 maja 2024.” | ✅ |
| RU33 | ANACHRONISM: +1 dzień w tolerancji | przeszłe, źródło 2024-03-02 [t_A=2024-03-01] | brak problemów | ✅ |
| RU34 | ANACHRONISM: +2 dni | przeszłe, źródło 2024-03-03 [t_A=2024-03-01] | ANACHRONISM (high, Δ=2 dni) | ✅ |
| RU35 | ANACHRONISM dla czasu teraźniejszego | tense=present, źródło 2024-05-30 [t_A=2024-03-01] | ANACHRONISM (high, Δ=90 dni) | ✅ |
| RU36 | zapowiedź (tense=future) to nie anachronizm | tense=future, źródło 2024-05-30 [t_A=2024-03-01] | brak problemów | ✅ |
| RU37 | rola future to nie anachronizm | role=future, tense=past, źródło 2024-05-30 [t_A=2024-03-01] | brak problemów | ✅ |
| RU38 | status unknown też podlega regule | status=unknown, źródło 2024-05-30 [t_A=2024-03-01] | ANACHRONISM (high, Δ=90 dni) | ✅ |
| RU39 | źródło z datą miesięczną | przeszłe, źródło 2024-04 (miesiąc) [t_A=2024-03-01] | ANACHRONISM (high, Δ=31 dni); opis zawiera „nastąpiło dopiero w kwietniu 2024.” | ✅ |
| RU40 | DATE_MISMATCH + ANACHRONISM naraz | tekst 2024-02-10, źródło 2024-05-30 [t_A=2024-03-01] | DATE_MISMATCH (high, Δ=110 dni) → ANACHRONISM (high, Δ=90 dni) | ✅ |
| RU41 | ANACHRONISM + BEFORE_SOURCES | przeszłe, źródło 2024-05-30 opublikowane 2024-06-01 [t_A=2024-03-01] | ANACHRONISM (high, Δ=90 dni) → BEFORE_SOURCES (low, Δ=92 dni) | ✅ |
| RU42 | FUTURE_AS_PAST: plan na czerwiec 2025 | przeszłe, źródło: plan 2025-06 [t_A=2024-03-01] | FUTURE_AS_PAST (high); opis: „Tekst podaje »zawalenie mostu« jako fakt dokonany, a według źródła »Raport« to plan na czerwiec 2025.” | ✅ |
| RU43 | FUTURE_AS_PAST: plan bez daty | przeszłe, źródło: plan bez daty [t_A=2024-03-01] | FUTURE_AS_PAST (high); opis zawiera „to dopiero zapowiedź.” | ✅ |
| RU44 | plan z przeszłości mógł się już ziścić | przeszłe, źródło: plan 2023-06 [t_A=2024-03-01] | brak problemów | ✅ |
| RU45 | plan kończy się dzień przed tekstem (tolerancja) | przeszłe, źródło: plan 2024-02-29 [t_A=2024-03-01] | FUTURE_AS_PAST (high) | ✅ |
| RU46 | plan kończy się 2 dni przed tekstem | przeszłe, źródło: plan 2024-02-28 [t_A=2024-03-01] | brak problemów | ✅ |
| RU47 | tekst w czasie teraźniejszym | tense=present, źródło: plan 2025-06 [t_A=2024-03-01] | brak problemów | ✅ |
| RU48 | tekst sam podaje to jako zapowiedź | role=future, źródło: plan 2025-06 [t_A=2024-03-01] | brak problemów | ✅ |
| RU49 | FUTURE_AS_PAST bez daty tekstu | przeszłe, źródło: plan 2025-06 [t_A=brak] | FUTURE_AS_PAST (high) | ✅ |
| RU50 | plan w przyszłości: FUTURE_AS_PAST, nie ANACHRONISM | przeszłe, źródło: plan 2024-05-30 [t_A=2024-03-01] | FUTURE_AS_PAST (high) | ✅ |
| RU51 | zdarzenie dokonane w przeszłości → OK | przeszłe, źródło: occurred 2023-06 [t_A=2024-03-01] | brak problemów | ✅ |
| RU52 | „środa 12 marca 2024” (wtorek) | 2024-03-12 + „środa” [t_A=brak] | INTERNAL_INCONSISTENCY (medium); opis: „Tekst podaje, że 12 marca 2024 to środa, ale ten dzień to wtorek.” | ✅ |
| RU53 | poprawny dzień tygodnia | 2024-03-12 + „wtorek” [t_A=brak] | brak problemów | ✅ |
| RU54 | odmiana „we wtorek” | 2024-03-12 + „we wtorek” [t_A=brak] | brak problemów | ✅ |
| RU55 | odmiana „w czwartek” (błędna) | 2024-03-12 + „w czwartek” [t_A=brak] | INTERNAL_INCONSISTENCY (medium) | ✅ |
| RU56 | data nie podana wprost | 2024-03-12 + „środa”, absolute_given=False [t_A=brak] | brak problemów | ✅ |
| RU57 | data miesięczna z dniem tygodnia | 2024-03 + „środa” [t_A=brak] | brak problemów | ✅ |
| RU58 | nierozpoznany dzień tygodnia | 2024-03-12 + „jutro” [t_A=brak] | brak problemów | ✅ |
| RU59 | 29 lutego 2024 to czwartek | 2024-02-29 + „piątek” [t_A=brak] | INTERNAL_INCONSISTENCY (medium); opis zawiera „ale ten dzień to czwartek.” | ✅ |
| RU60 | 1 stycznia 2025 to środa | 2025-01-01 + „środa” [t_A=brak] | brak problemów | ✅ |
| RU61 | Boże Narodzenie 2024 to środa | 2024-12-25 + „niedziela” [t_A=brak] | INTERNAL_INCONSISTENCY (medium); opis zawiera „ale ten dzień to środa.” | ✅ |
| RU62 | skrót „Śr.” | 2024-03-13 + „Śr.” [t_A=brak] | brak problemów | ✅ |
| RU63 | dzień tygodnia bez daty | brak daty + „środa” [t_A=brak] | brak problemów | ✅ |
| RU64 | „wczoraj” vs 2 marca | abs 2024-03-02, „wczoraj” = 2024-03-19 [t_A=2024-03-20] | INTERNAL_INCONSISTENCY (medium, Δ=17 dni); opis: „Tekst określa »zawalenie mostu« jako »wczoraj« (19 marca 2024), a jednocześnie datuje je na 2 marca 2024.” | ✅ |
| RU65 | „wczoraj” zgodne | abs 2024-03-19, „wczoraj” = 2024-03-19 [t_A=2024-03-20] | brak problemów | ✅ |
| RU66 | „wczoraj” ±1 dzień | abs 2024-03-18, „wczoraj” = 2024-03-19 [t_A=2024-03-20] | brak problemów | ✅ |
| RU67 | „wczoraj” o 2 dni obok | abs 2024-03-17, „wczoraj” = 2024-03-19 [t_A=2024-03-20] | INTERNAL_INCONSISTENCY (medium, Δ=2 dni) | ✅ |
| RU68 | „w tym miesiącu” zawiera dzień | abs 2024-03-05, względne = 2024-03 (miesiąc) [t_A=2024-03-20] | brak problemów | ✅ |
| RU69 | „w zeszłym tygodniu” poza tygodniem | abs 2024-03-05, względne = 2024-03-10…16 (week) [t_A=2024-03-20] | INTERNAL_INCONSISTENCY (medium, Δ=5 dni); opis zawiera „jako »w zeszłym tygodniu« (w okresie 10–16 marca 2024)” | ✅ |
| RU70 | nieprzeliczalne wyrażenie względne | abs 2024-03-02, „niedawno” = brak [t_A=2024-03-20] | brak problemów | ✅ |
| RU71 | brak daty bezwzględnej | „wczoraj”, absolute_given=False [t_A=2024-03-20] | brak problemów | ✅ |
| RU72 | przeszłe zdarzenie po dacie tekstu | przeszłe, tekst datuje 2024-05-01 [t_A=2024-03-20] | INTERNAL_INCONSISTENCY (medium, Δ=42 dni); opis: „Tekst z 20 marca 2024 opisuje »zawalenie mostu« jako przeszłe, choć sam datuje je na 1 maja 2024.” | ✅ |
| RU73 | +1 dzień w tolerancji | przeszłe, 2024-03-21 [t_A=2024-03-20] | brak problemów | ✅ |
| RU74 | +2 dni | przeszłe, 2024-03-22 [t_A=2024-03-20] | INTERNAL_INCONSISTENCY (medium, Δ=2 dni) | ✅ |
| RU75 | zapowiedź w przyszłości | tense=future, 2024-05-01 [t_A=2024-03-20] | brak problemów | ✅ |
| RU76 | czas teraźniejszy | tense=present, 2024-05-01 [t_A=2024-03-20] | brak problemów | ✅ |
| RU77 | rola reference | role=reference, 2024-05-01 [t_A=2024-03-20] | brak problemów | ✅ |
| RU78 | dane „na dzień” po dacie tekstu | role=data_as_of, przeszłe, 2024-05-01 [t_A=2024-03-20] | INTERNAL_INCONSISTENCY (medium, Δ=42 dni) | ✅ |
| RU79 | bez daty tekstu nie ma kolejności | przeszłe, 2024-05-01 [t_A=brak] | brak problemów | ✅ |
| RU80 | miesiąc po dacie tekstu | przeszłe, 2024-04 (miesiąc) [t_A=2024-03-20] | INTERNAL_INCONSISTENCY (medium, Δ=12 dni) | ✅ |
| RU81 | dane z 2015 jako aktualne | data_as_of 2015 (rok), recency 0.8 [t_A=2024-03-01] | STALE_DATA (medium, Δ=2983 dni); opis: „Dane o »bezrobocie« pochodzą z 2015 r., a tekst z 1 marca 2024 przedstawia je jako aktualne.” | ✅ |
| RU82 | dane z lutego 2023 (367 dni) | data_as_of 2023-02 (miesiąc) [t_A=2024-03-01] | STALE_DATA (medium, Δ=367 dni); opis zawiera „pochodzą z lutego 2023” | ✅ |
| RU83 | dane z marca 2023 (336 dni) → OK | data_as_of 2023-03 (miesiąc) [t_A=2024-03-01] | brak problemów | ✅ |
| RU84 | granica: 366 dni | data_as_of 2023-03-01 [t_A=2024-03-01] | STALE_DATA (medium, Δ=366 dni); opis zawiera „pochodzą z 1 marca 2023” | ✅ |
| RU85 | granica: 365 dni → OK | data_as_of 2023-03-02 [t_A=2024-03-01] | brak problemów | ✅ |
| RU86 | brak ramowania „obecnie” | data_as_of 2015, recency 0.5 [t_A=2024-03-01] | brak problemów | ✅ |
| RU87 | rola event to nie dane | role=event, 2015, recency 0.8 [t_A=2024-03-01] | brak problemów | ✅ |
| RU88 | data danych ze źródła | data_as_of bez daty w tekście, źródło 2015 (rok) [t_A=2024-03-01] | STALE_DATA (medium, Δ=2983 dni) | ✅ |
| RU89 | brak daty tekstu | data_as_of 2015 [t_A=brak] | brak problemów | ✅ |
| RU90 | dane kwartalne | data_as_of 2022-Q4 [t_A=2024-03-01] | STALE_DATA (medium, Δ=426 dni); opis zawiera „pochodzą z 4. kwartału 2022 r.” | ✅ |
| RU91 | tekst 9 dni przed źródłem | źródło »TVN« opublikowane 2024-03-20 [t_A=2024-03-11] | BEFORE_SOURCES (low, Δ=9 dni); opis: „Tekst z 11 marca 2024 ukazał się przed najwcześniejszą publikacją w dopasowanych źródłach (20 marca 2024).” | ✅ |
| RU92 | dzień przed źródłem (tolerancja) | źródło opublikowane 2024-03-20 [t_A=2024-03-19] | brak problemów | ✅ |
| RU93 | 2 dni przed źródłem | źródło opublikowane 2024-03-20 [t_A=2024-03-18] | BEFORE_SOURCES (low, Δ=2 dni) | ✅ |
| RU94 | liczy się najwcześniejsze dopasowane źródło | źródła opublikowane 2024-03-20 i 2024-03-15 [t_A=2024-03-10] | BEFORE_SOURCES (low, Δ=5 dni) | ✅ |
| RU95 | niedopasowane źródło jest pomijane | dopasowane 2024-03-20, niedopasowane 2024-01-01 [t_A=2024-03-11] | BEFORE_SOURCES (low, Δ=9 dni) | ✅ |
| RU96 | sortowanie: waga, potem pozycja | 3 daty: weekday@50 (medium), mismatch@10 (high), mismatch@30 (medium) [t_A=brak] | DATE_MISMATCH (high, Δ=731 dni) → DATE_MISMATCH (medium, Δ=2 dni) → INTERNAL_INCONSISTENCY (medium) | ✅ |
| RU97 | jedna data, dwa problemy | „środa 12 marca 2024”, źródło 2022-03-12 [t_A=brak] | DATE_MISMATCH (high, Δ=731 dni) → INTERNAL_INCONSISTENCY (medium) | ✅ |
| RU98 | brak dat w tekście | 0 dat [t_A=2024-03-01] | brak problemów | ✅ |
| RU99 | issue niesie cytaty, offsety i id źródła | DATE_MISMATCH dla cytatu »12 marca 2024« @7–20, źródło s1 »12 marca 2022« | input_quote, start=7, end=20, source_id=s1, source_quote wypełnione | ✅ |

## SK: skipped_checks: pominięte reguły i powody (7)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| SK01 | brak daty i brak źródeł | t_A=brak, sources=[] | 9 wpisów: ANACHRONISM: brak daty publikacji tekstu; ANACHRONISM: brak źródeł prawdy; BEFORE_SOURCES: brak daty publikacji tekstu; BEFORE_SOURCES: brak źródeł prawdy; DATE_MISMATCH: brak źródeł prawdy; FUTURE_AS_PAST: brak źródeł prawdy; OUTDATED_AS_CURRENT: brak daty publikacji tekstu; OUTDATED_AS_CURRENT: brak źródeł prawdy; STALE_DATA: brak daty publikacji tekstu | ✅ |
| SK02 | jest data, brak źródeł | t_A=2024-03-01, sources=[] | 5 wpisów: ANACHRONISM: brak źródeł prawdy; BEFORE_SOURCES: brak źródeł prawdy; DATE_MISMATCH: brak źródeł prawdy; FUTURE_AS_PAST: brak źródeł prawdy; OUTDATED_AS_CURRENT: brak źródeł prawdy | ✅ |
| SK03 | są źródła, brak daty | t_A=brak, sources=[PAP] | 4 wpisów: ANACHRONISM: brak daty publikacji tekstu; BEFORE_SOURCES: brak daty publikacji tekstu; OUTDATED_AS_CURRENT: brak daty publikacji tekstu; STALE_DATA: brak daty publikacji tekstu | ✅ |
| SK04 | komplet danych | t_A=2024-03-12, dopasowane źródło z published_at | 0 wpisów: [] | ✅ |
| SK05 | dopasowane źródło bez daty publikacji | t_A=2024-03-01, źródło »Raport« bez published_at | 1 wpisów: BEFORE_SOURCES: żadne dopasowane źródło nie ma daty publikacji | ✅ |
| SK06 | źródła są, ale nic nie dopasowano | t_A=2024-03-01, 0 dopasowań | 1 wpisów: BEFORE_SOURCES: żadne dopasowane źródło nie ma daty publikacji | ✅ |
| SK07 | zduplikowane wpisy z wejścia są scalane | 2× ten sam SkippedCheck przekazany z build_items | 2 wpisów: BEFORE_SOURCES: żadne dopasowane źródło nie ma daty publikacji; INTERNAL_INCONSISTENCY: x | ✅ |

## BD: build_dates_result(): odpowiedź LLM → DatesResult (28)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| BD01 | parametr article_date ma pierwszeństwo | article_date=2024-03-12, LLM: article_date_in_text=2020-01-01 | article_date = 2024-03-12 | ✅ |
| BD02 | data publikacji z treści tekstu | article_date=None, LLM: article_date_in_text=2024-03-12 | article_date = 2024-03-12 | ✅ |
| BD03 | data publikacji tylko z miesiącem jest ignorowana | article_date_in_text=2024-03 | article_date = None | ✅ |
| BD04 | data publikacji z elementu role=publication | element role=publication, iso 2024-03-15 | article_date = 2024-03-15 | ✅ |
| BD05 | publication z samym rokiem nie wystarcza | element role=publication, iso 2024 (rok) | article_date = None | ✅ |
| BD06 | brak daty tekstu → reguły pominięte | brak article_date i brak daty w tekście | article_date=None; skipped zawiera OUTDATED_AS_CURRENT: brak daty publikacji tekstu | ✅ |
| BD07 | „wczoraj” przeliczone względem daty tekstu | „Wczoraj” bez daty wprost, article_date=2024-03-20 | extracted[0].date_from = date_to = 2024-03-19 | ✅ |
| BD08 | „wczoraj” bez daty tekstu | „Wczoraj” bez daty wprost, article_date=None | date_from=None; skipped: INTERNAL_INCONSISTENCY „nie można przeliczyć »wczoraj« bez daty publikacji tekstu” | ✅ |
| BD09 | „Wczoraj, 2 marca” w tekście z 20 marca | absolute 2024-03-02 + „wczoraj”, article_date=2024-03-20 | date_from=2024-03-02; INTERNAL_INCONSISTENCY (medium, Δ=17); dates_consistent=False | ✅ |
| BD10 | data względna w źródle liczona od jego publikacji | źródło „Wczoraj wieczorem…” opublikowane 2019-06-04, LLM podał 2019-06-10 | source_date_from = 2019-06-03 (nadpisuje LLM) | ✅ |
| BD11 | nieznane id źródła | match.source_id = „nie-ma” | brak dopasowania; data w unverified | ✅ |
| BD12 | found=false | match.found = false | unverified = [»Właśnie zawalił się most« (zawalenie)] | ✅ |
| BD13 | rola reference nie trafia do unverified | role=reference bez dopasowania | unverified = [] | ✅ |
| BD14 | rola publication nie trafia do unverified | role=publication bez dopasowania | unverified = [] | ✅ |
| BD15 | rola future i data_as_of trafiają do unverified | role=future i role=data_as_of bez dopasowania | unverified ma 2 wpisy | ✅ |
| BD16 | recency_framing przycinane do [0, 1] | recency 1.5 i −0.3 | recency_framing = 1.0 i 0.0 | ✅ |
| BD17 | pusty opis what → cytat | what = „” | what = „Dane z 2015 r.” | ✅ |
| BD18 | zmyślony cytat jest odrzucany | 2 daty, w tym jedna z cytatem spoza tekstu | extracted = [d1] | ✅ |
| BD19 | tylko problem niskiej wagi | tekst z 2024-03-11, źródło opublikowane 2024-03-20 | issues = [BEFORE_SOURCES (low)]; dates_consistent = True | ✅ |
| BD20 | problem średniej wagi psuje spójność | „środa 12 marca 2024” (wtorek) | dates_consistent = False | ✅ |
| BD21 | tekst bez dat | LLM: dates = [] | dates_consistent = True, extracted = [], issues = [] | ✅ |
| BD22 | cytat odnaleziony bez względu na wielkość liter | LLM: quote „właśnie zawalił się most” (mała litera) | extracted[0].quote = „Właśnie zawalił się most” (z tekstu), start=44 | ✅ |
| BD23 | cytat źródła z drobną literówką | source_quote „Wczoraj wieczorem zawalilo się przęsło mostu” | dopasowanie przyjęte; source_quote z oryginału źródła | ✅ |
| BD24 | kategoria tekstu przekazana dalej | text_category = economic | text_category = economic | ✅ |
| BD25 | granularność week z LLM | iso 2024-03-10…2024-03-16, granularity=week | extracted[0].granularity = week | ✅ |
| BD26 | stary news jako bieżący (pełny przepływ) | „Właśnie zawalił się most” (recency 0.95, breaking), źródło PAP 2019-06-03, tekst z 2024-03-12 | OUTDATED_AS_CURRENT (high, Δ=1744); dates_consistent = False | ✅ |
| BD27 | offset problemu wskazuje cytat w tekście | jak BD26 | text[issue.start:issue.end] == issue.input_quote | ✅ |
| BD28 | pusty tekst nie wywołuje LLM | analyze_dates(„   ”) z atrapą LLM, która rzuca wyjątek | dates_consistent = True, extracted = [], bez wywołania LLM | ✅ |

## MA: build_manipulation_result(): odpowiedź LLM → fragmenty (39)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| MA01 | confidence 0.29 → szum | 1 fragment, confidence=0.29 | fragments=[], dropped=0, detected=False | ✅ |
| MA02 | confidence 0.3 → zostaje, ale nie przesądza | confidence=0.3 | 1 fragment, detected=False | ✅ |
| MA03 | confidence 0.49 | confidence=0.49 | 1 fragment, detected=False | ✅ |
| MA04 | confidence 0.5 → wykryto | confidence=0.5 | detected=True | ✅ |
| MA05 | confidence > 1 przycięte | confidence=1.7 | confidence=1.0 | ✅ |
| MA06 | confidence ujemne | confidence=−0.5 | fragments=[] | ✅ |
| MA07 | duplikat: zostaje wyższa pewność | ten sam cytat i kategoria, confidence 0.6 i 0.9 | 1 fragment, confidence=0.9 | ✅ |
| MA08 | ten sam cytat, dwie kategorie | A + F na „skandaliczna zdrada rządu” | 2 wpisy z tym samym zakresem; counts A=1, F=1 | ✅ |
| MA09 | podtyp wielkimi literami | LACK_OF_SOURCE, subtype=„UNRELIABLE” | subtype=unreliable | ✅ |
| MA10 | podtyp ze spacjami | subtype=„ none ” | subtype=none | ✅ |
| MA11 | podtyp unverifiable | LACK_OF_SOURCE, subtype=unverifiable | subtype=unverifiable | ✅ |
| MA12 | podtyp inadequate | LACK_OF_SOURCE, subtype=inadequate | subtype=inadequate | ✅ |
| MA13 | nieznany podtyp | subtype=„foo” | subtype=None | ✅ |
| MA14 | podtyp poza kategorią E | EMOTIONAL_LANGUAGE, subtype=none | subtype=None | ✅ |
| MA15 | wskaźniki oczyszczone | indicators=[„  a ”, „”, „   ”] | indicators=[„a”] | ✅ |
| MA16 | dowód z nieznanego źródła | source_id=„nie-ma” | source_evidence=None | ✅ |
| MA17 | pusty dowód | source_id=kgp, source_evidence=„” | source_evidence=None | ✅ |
| MA18 | poprawny dowód | source_id=kgp, cytat ze źródła | source_evidence={kgp, cytat} | ✅ |
| MA19 | id źródła ze spacjami | source_id=„ kgp ” | source_evidence.source_id=kgp | ✅ |
| MA20 | dowód innymi literami → oryginał ze źródła | source_evidence małymi literami | quote w oryginalnej pisowni źródła | ✅ |
| MA21 | zmyślony dowód | source_evidence spoza źródła | fragment zostaje, source_evidence=None | ✅ |
| MA22 | sortowanie po pozycji | fragmenty podane od końca tekstu | rosnąco po start | ✅ |
| MA23 | zmyślony cytat odrzucony | quote spoza tekstu | fragments=[], dropped_fragments=1 | ✅ |
| MA24 | zmyślony cytat z niską pewnością | quote spoza tekstu, confidence=0.1 | dropped_fragments=0 (odrzucony wcześniej jako szum) | ✅ |
| MA25 | liczniki dla wszystkich kategorii | 1 fragment A | counts ma 7 kluczy A–G, suma = 1 | ✅ |
| MA26 | nazwa kategorii EMOTIONAL_LANGUAGE | category=EMOTIONAL_LANGUAGE | category_name zaczyna się od „A. Język emocjonalny” | ✅ |
| MA27 | nazwa kategorii FEAR_APPEAL | category=FEAR_APPEAL | category_name zaczyna się od „B. Straszenie” | ✅ |
| MA28 | nazwa kategorii CONSPIRACY_FRAMING | category=CONSPIRACY_FRAMING | category_name zaczyna się od „C. Sugerowanie spisku” | ✅ |
| MA29 | nazwa kategorii FALSE_URGENCY | category=FALSE_URGENCY | category_name zaczyna się od „D. Fałszywa pilność” | ✅ |
| MA30 | nazwa kategorii LACK_OF_SOURCE | category=LACK_OF_SOURCE | category_name zaczyna się od „E. Brak źródła” | ✅ |
| MA31 | nazwa kategorii EXAGGERATION | category=EXAGGERATION | category_name zaczyna się od „F. Wyolbrzymienie” | ✅ |
| MA32 | nazwa kategorii CHERRY_PICKING | category=CHERRY_PICKING | category_name zaczyna się od „G. Cherry-picking” | ✅ |
| MA33 | atrybucja quoted zachowana | attribution=quoted | attribution=quoted | ✅ |
| MA34 | cytat innymi literami → tekst oryginału | quote=„SKANDALICZNA ZDRADA RZĄDU” | quote=„skandaliczna zdrada rządu”, start=3 | ✅ |
| MA35 | pola tekstowe oczyszczone | explanation/test_answer ze spacjami | bez spacji na brzegach | ✅ |
| MA36 | tekst neutralny | fragments=[] | detected=False, score=0, wszystkie liczniki 0 | ✅ |
| MA37 | cytat cudzy z wysoką pewnością nadal wykryty | attribution=quoted, confidence=0.9 | detected=True | ✅ |
| MA38 | offsety zgodne z tekstem | 4 różne fragmenty | text[start:end] == quote dla każdego | ✅ |
| MA39 | pusty tekst nie wywołuje LLM | analyze_manipulation(„  \n ”) z atrapą, która rzuca wyjątek | fragments=[], score=0, bez wywołania LLM | ✅ |

## SC: score_fragments(): wynik 0–100 (12)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| SC01 | brak fragmentów | 10 słów; fragmenty: brak | 0 | ✅ |
| SC02 | 1 fragment autora | 10 słów; fragmenty: 1.0/author | 28 | ✅ |
| SC03 | 1 cytat cudzy (waga 0.5) | 10 słów; fragmenty: 1.0/quoted | 15 | ✅ |
| SC04 | 1 fragment z pewnością 0.5 | 10 słów; fragmenty: 0.5/author | 15 | ✅ |
| SC05 | 3 fragmenty | 10 słów; fragmenty: 1.0/author, 1.0/author, 1.0/author | 63 | ✅ |
| SC06 | 1 fragment w 100 słowach | 100 słów; fragmenty: 1.0/author | 28 | ✅ |
| SC07 | 1 fragment w 200 słowach | 200 słów; fragmenty: 1.0/author | 15 | ✅ |
| SC08 | 1 fragment w 300 słowach | 300 słów; fragmenty: 1.0/author | 11 | ✅ |
| SC09 | 10 fragmentów | 10 słów; fragmenty: 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author | 96 | ✅ |
| SC10 | 2 autora + 2 cudze | 10 słów; fragmenty: 1.0/author, 1.0/author, 1.0/quoted, 1.0/quoted | 63 | ✅ |
| SC11 | nasycenie przy 30 fragmentach | 10 słów; fragmenty: 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author, 1.0/author | 100 | ✅ |
| SC12 | pusty tekst z fragmentem | 0 słów; fragmenty: 1.0/author | 28 | ✅ |

## PR: Prompty: nagłówek i źródła (5)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| PR01 | brak źródeł | render_sources([]) | „(brak źródeł prawdy)” | ✅ |
| PR02 | atrybuty źródła | źródło z id, tytułem, datą i url | <zrodlo id="s1" tytul="PAP" data_publikacji="2024-03-12" url=…> | ✅ |
| PR03 | przycinanie długich źródeł | treść 20506 znaków | pierwsze 20000 znaków, bez końcówki | ✅ |
| PR04 | data tekstu w nagłówku | article_date=2024-04-01 | „Data publikacji tekstu: 2024-04-01” + <tekst>…</tekst> | ✅ |
| PR05 | nieznana data tekstu | article_date=None | „Data publikacji tekstu: nieznana …” | ✅ |

## PI: Pipeline analyze()/analyze_async() z atrapą LLM (8)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| PI01 | synchroniczne analyze() | analyze(tekst, [], 2024-04-01, atrapa) | counts[A]=1, article_date=2024-04-01 | ✅ |
| PI02 | analyze() w pętli zdarzeń | analyze() wywołane wewnątrz asyncio.run | RuntimeError „…użyj await analyze_async()” | ✅ |
| PI03 | sources=None | analyze(tekst, None) | działa; skipped: brak źródeł prawdy | ✅ |
| PI04 | źródła jako słowniki z aliasami | {source_id, body, date} | oba prompty zawierają <zrodlo id="kgp" data_publikacji="2024-03-01"> | ✅ |
| PI05 | dwa wywołania LLM | analyze(tekst) | wywołano schematy LLMManipulationResponse i LLMDatesResponse | ✅ |
| PI06 | błąd LLM | atrapa rzuca LLMError | LLMError propagowany do wywołującego | ✅ |
| PI07 | pusty tekst | analyze_async(„”) | 0 wywołań LLM, wynik neutralny | ✅ |
| PI08 | wynik serializowalny do JSON | model_dump(mode=json) | klucze manipulation, dates; daty jako ISO | ✅ |

## LV: Na żywo z LLM (wymaga klucza i RUN_LLM_TESTS=1) (9)

| ID | Przypadek | Wejście | Oczekiwany wynik | Status |
|---|---|---|---|---|
| LV01 | przykład „A_emocje” | EXAMPLES['A_emocje'] → prawdziwy LLM | counts[EMOTIONAL_LANGUAGE] ≥ 1, detected=True | ✅ |
| LV02 | przykład „B_straszenie” | EXAMPLES['B_straszenie'] → prawdziwy LLM | counts[FEAR_APPEAL] ≥ 1 | ✅ |
| LV03 | przykład „C_spisek” | EXAMPLES['C_spisek'] → prawdziwy LLM | counts[CONSPIRACY_FRAMING] ≥ 1 | ✅ |
| LV04 | przykład „D_pilnosc” | EXAMPLES['D_pilnosc'] → prawdziwy LLM | counts[FALSE_URGENCY] ≥ 1 | ✅ |
| LV05 | przykład „E_brak_zrodla” | EXAMPLES['E_brak_zrodla'] → prawdziwy LLM | counts[LACK_OF_SOURCE] ≥ 1 | ✅ |
| LV06 | przykład „F_wyolbrzymienie” | EXAMPLES['F_wyolbrzymienie'] → prawdziwy LLM | counts[EXAGGERATION] ≥ 1 | ✅ |
| LV07 | przykład „G_cherry_picking” | EXAMPLES['G_cherry_picking'] → prawdziwy LLM | CHERRY_PICKING z source_evidence | ✅ |
| LV08 | przykład „neutralny” | EXAMPLES['neutralny'] → prawdziwy LLM | 0 fragmentów, score=0, dates_consistent=True, 0 problemów | ✅ |
| LV09 | przykład „stary_news_jako_nowy” | EXAMPLES['stary_news_jako_nowy'] → prawdziwy LLM | OUTDATED_AS_CURRENT + INTERNAL_INCONSISTENCY, dates_consistent=False | ✅ |
