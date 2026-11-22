"""Katalog przypadków maskowania: wejście i oczekiwany tekst po maskowaniu.

``MASKED`` – dane osobowe, które muszą zniknąć. ``KEPT`` – tekst, który musi
zostać bez zmian: imiona i nazwiska oraz liczby potrzebne do sprawdzania faktów.
Nowy błąd? Najpierw dopisz go tutaj, potem poprawiaj reguły.
"""

from __future__ import annotations

from typing import NamedTuple


class Case(NamedTuple):
    id: str
    text: str
    expected: str


MASKED: list[Case] = [
    # PESEL
    Case("P1", "Mój PESEL to 44051401359.", "Mój PESEL to [PESEL_1]."),
    Case("P2", "Urodzona w 2002: 02270803624", "Urodzona w [DATA_URODZENIA_1]: [PESEL_1]"),
    Case("P3", "pesel: 12345678901 (z błędem)", "pesel: [PESEL_1] (z błędem)"),
    # NIP, REGON
    Case("N1", "NIP firmy: 526-025-02-74", "NIP firmy: [NIP_1]"),
    Case("N2", "Faktura na PL5260250274.", "Faktura na [NIP_1]."),
    Case("N3", "nip 526 025 02 74", "nip [NIP_1]"),
    Case("N4", "Numer 526-02-50-274 w KRS", "Numer [NIP_1] w KRS"),
    Case("R1", "REGON 123456785", "REGON [REGON_1]"),
    Case("R2", "Spółka 12345678512347 działa od 2010.", "Spółka [REGON_1] działa od 2010."),
    # Konta i karty
    Case(
        "K1",
        "Przelej na PL61 1090 1014 0000 0712 1981 2874 dziś.",
        "Przelej na [NR_KONTA_1] dziś.",
    ),
    Case("K2", "konto 61109010140000071219812874", "konto [NR_KONTA_1]"),
    Case("K3", "IBAN DE89 3704 0044 0532 0130 00", "IBAN [NR_KONTA_1]"),
    Case("K4", "karta 4111 1111 1111 1111 wygasa", "karta [KARTA_1] wygasa"),
    Case("K5", "Płaciłem kartą 5555-5555-5555-4444.", "Płaciłem kartą [KARTA_1]."),
    # Dokumenty
    Case("D1", "Dowód ABA300000 zgubiony.", "Dowód [DOWOD_1] zgubiony."),
    Case("D2", "seria i numer dowodu: ABC 123456", "seria i numer dowodu: [DOWOD_1]"),
    Case("D3", "Paszport nr EA 1234567 jest ważny.", "Paszport nr [PASZPORT_1] jest ważny."),
    # Telefony
    Case("T1", "Zadzwoń: +48 600 100 200", "Zadzwoń: [TELEFON_1]"),
    Case("T2", "tel. 600100200", "tel. [TELEFON_1]"),
    Case("T3", "Numer 601-222-333 nie odpowiada.", "Numer [TELEFON_1] nie odpowiada."),
    Case("T4", "Biuro: (22) 123 45 67.", "Biuro: [TELEFON_1]."),
    Case("T5", "Biuro: 22 123 45 67", "Biuro: [TELEFON_1]"),
    Case("T6", "0048 22 123 45 67", "[TELEFON_1]"),
    Case(
        "T7",
        "Dzwonił z 600 100 200, potem znowu z 600100200 i z 512 000 111.",
        "Dzwonił z [TELEFON_1], potem znowu z [TELEFON_1] i z [TELEFON_2].",
    ),
    # Internet
    Case("E1", "Pisz na jan.kowalski+fb@gmail.com.", "Pisz na [EMAIL_1]."),
    Case("E2", "Kontakt: anna_nowak@poczta.onet.pl", "Kontakt: [EMAIL_1]"),
    Case("I1", "Logował się z 83.12.201.7.", "Logował się z [IP_1]."),
    # Adresy
    Case("A1", "Mieszka na ul. Długiej 15/3 w Gdańsku.", "Mieszka na [ADRES_1] w Gdańsku."),
    Case("A2", "al. Jana Pawła II 12 m. 4", "[ADRES_1]"),
    Case("A3", "ulica 3 Maja 7a", "[ADRES_1]"),
    Case("A4", "os. Tysiąclecia 45, Katowice", "[ADRES_1], Katowice"),
    Case("A5", "Mieszkam w Gdańsku przy Długiej 15.", "Mieszkam w Gdańsku przy [ADRES_1]."),
    Case("A6", "Adres: Kwiatowa 7, 00-950 Warszawa", "Adres: [ADRES_1], [KOD_POCZTOWY_1] Warszawa"),
    Case("A7", "pl. Grunwaldzki 2/14", "[ADRES_1]"),
    # Daty urodzenia i pojazdy
    Case("B1", "Jan Nowak, ur. 12.03.1985 r.", "Jan Nowak, ur. [DATA_URODZENIA_1] r."),
    Case(
        "B2",
        "urodziła się 5 maja 1990 w Łodzi",
        "urodziła się [DATA_URODZENIA_1] w Łodzi",
    ),
    Case("B3", "data urodzenia: 1985-03-12", "data urodzenia: [DATA_URODZENIA_1]"),
    Case(
        "V1", "Auto o nr rej. WA 12345 odjechało.", "Auto o nr rej. [NR_REJESTRACYJNY_1] odjechało."
    ),
    Case("V2", "tablice rejestracyjne KR4F123", "tablice rejestracyjne [NR_REJESTRACYJNY_1]"),
    # Wszystko naraz: imię i nazwisko zostają
    Case(
        "X1",
        "Anna Nowak (PESEL 44051401359, tel. +48 600 100 200, anna@nowak.pl) "
        "mieszka przy ul. Polnej 3, 61-001 Poznań.",
        "Anna Nowak (PESEL [PESEL_1], tel. [TELEFON_1], [EMAIL_1]) "
        "mieszka przy [ADRES_1], [KOD_POCZTOWY_1] Poznań.",
    ),
]

# Naturalne wiadomości: bez kropek, małymi literami, z innymi separatorami.
MASKED += [
    Case(
        "M1", "zadzwon 600 100200 albo tel 600.100.200", "zadzwon [TELEFON_1] albo tel [TELEFON_1]"
    ),
    Case("M2", "Proszę oddzwonić 48 600 100 200.", "Proszę oddzwonić [TELEFON_1]."),
    Case("M3", "mój nr to 6OO 1OO 2OO", "mój nr to [TELEFON_1]"),
    Case("M4", "tel: 22.123.45.67", "tel: [TELEFON_1]"),
    Case("M5", "mój numer 512345678, dzwońcie", "mój numer [TELEFON_1], dzwońcie"),
    Case("M6", "mój pesel 4405 1401 359 jakby co", "mój pesel [PESEL_1] jakby co"),
    Case("M7", "pesel: 44-05-14-01359", "pesel: [PESEL_1]"),
    Case("M8", "dowód abc123456", "dowód [DOWOD_1]"),
    Case("M9", "ul długa 15", "[ADRES_1]"),
    Case(
        "M10",
        "mieszkam ul Długa 15, 80-831 gdańsk",
        "mieszkam [ADRES_1], [KOD_POCZTOWY_1] gdańsk",
    ),
    Case("M11", "kod 80831 Gdańsk", "kod [KOD_POCZTOWY_1] Gdańsk"),
    Case("M12", "mieszkam w Gdańsku, Długa 15/3.", "mieszkam w Gdańsku, [ADRES_1]."),
    Case("M13", "Sąsiad z Długiej 15 m 3 mówił", "Sąsiad z [ADRES_1] mówił"),
    Case("M14", "mieszkam na ulicy Długiej piętnaście", "mieszkam na [ADRES_1]"),
    Case("M15", "jestem zameldowany przy Kwiatowej 7a", "jestem zameldowany przy [ADRES_1]"),
    Case(
        "M16",
        "Urodziłam się 12 marca 85, mieszkam w Łodzi.",
        "Urodziłam się [DATA_URODZENIA_1], mieszkam w Łodzi.",
    ),
    Case(
        "M17",
        "mam urodziny 12.03, rocznik 1985",
        "mam urodziny [DATA_URODZENIA_1], rocznik [DATA_URODZENIA_2]",
    ),
    Case("M18", "Piszcie na jan kowalski małpa gmail kropka com", "Piszcie na jan [EMAIL_1]"),
    Case("M19", "albo jan.kowalski(at)gmail.com", "albo [EMAIL_1]"),
    Case("M20", "mail: kasia [at] wp [dot] pl", "mail: [EMAIL_1]"),
    Case(
        "M21",
        "Insta @kasia_nowak_88, fb.com/kasia.nowak.123.",
        "Insta [PROFIL_1], [PROFIL_2].",
    ),
    Case(
        "M22",
        "https://www.facebook.com/kasia.nowak.123/",
        "[PROFIL_1]",
    ),
    Case(
        "M23",
        "Moje auto WA12345 stoi pod blokiem.",
        "Moje auto [NR_REJESTRACYJNY_1] stoi pod blokiem.",
    ),
    Case("M24", "KR 4F123 to mój samochód", "[NR_REJESTRACYJNY_1] to mój samochód"),
    Case("M25", "pracuję w Biedronce przy Długiej 5", "pracuję w Biedronce przy [ADRES_1]"),
    Case("M26", "Gdańsk, Długa 15/3", "Gdańsk, [ADRES_1]"),
    # Realne wiadomości (łańcuszki, zbiórki, ogłoszenia, seniorzy)
    Case(
        "R1",
        "uwaga sąsiedzi z bloku na Kasprowicza 8, ktoś się kręci",
        "uwaga sąsiedzi z bloku na [ADRES_1], ktoś się kręci",
    ),
    Case("R2", "nr karty 5168 4412 3456 7890 czy to prawda", "nr karty [KARTA_1] czy to prawda"),
    Case("R3", "ur 3.07.1999 to se zapisz", "ur [DATA_URODZENIA_1] to se zapisz"),
    Case("R4", "Nr KW KR1P/00123456/7", "Nr KW [KSIEGA_WIECZYSTA_1]"),
    Case("R5", "Call me +44 7911 123456 or later", "Call me [TELEFON_1] or later"),
    Case(
        "R6",
        "I live at 221B Baker Street, London NW1 6XE",
        "I live at [ADRES_1], London [KOD_POCZTOWY_1]",
    ),
    Case(
        "R7",
        "Nasz adres Świętojańska 45/2, Gdynia 81-391",
        "Nasz adres [ADRES_1], Gdynia [KOD_POCZTOWY_1]",
    ),
    Case(
        "R8",
        "jestem z 1987 r., urodzinki mam 3 maja",
        "jestem z [DATA_URODZENIA_1] r., urodzinki mam [DATA_URODZENIA_2]",
    ),
    Case("R9", "MAC 00:1A:2B:3C:4D:5E", "MAC [MAC_1]"),
    Case("R10", "seria i nr: AYZ-123456, wydany", "seria i nr: [DOWOD_1], wydany"),
    Case("R11", "zadzwoń do Niemiec +49 30 1234 5678", "zadzwoń do Niemiec [TELEFON_1]"),
    Case("R12", "mieszkam teraz na Wolskiej 23 m 81.", "mieszkam teraz na [ADRES_1]."),
    Case(
        "R13",
        "Mama Joanna, tel 698 123 456. Mieszkają w Radomiu na Struga 12/4",
        "Mama Joanna, tel [TELEFON_1]. Mieszkają w Radomiu na [ADRES_1]",
    ),
    Case(
        "R14",
        "Krzysztof Malinowski (ur. 1971, zam. Łomianki, ul. Warszawska 15) obiecał 500 zł",
        "Krzysztof Malinowski (ur. [DATA_URODZENIA_1], zam. Łomianki, [ADRES_1]) obiecał 500 zł",
    ),
    Case(
        "R15",
        "adres zameldowania: Toruń, Szeroka 7/3, 87-100",
        "adres zameldowania: Toruń, [ADRES_1], [KOD_POCZTOWY_1]",
    ),
    Case(
        "R16",
        "Znalezione pod Żabką na os. Piastowskim 22. Tel 533-019-888",
        "Znalezione pod Żabką na [ADRES_1]. Tel [TELEFON_1]",
    ),
    Case(
        "R17",
        "kontakt na WhatsApp +48 791 202 303 lub maila p.nowicki95@interia.pl, przyjadę na Bema 5a/12",
        "kontakt na WhatsApp [TELEFON_1] lub maila [EMAIL_1], przyjadę na [ADRES_1]",
    ),
    # Normalizacja: sklejone wiadomości, niewidoczne znaki, liczby słownie, pełna szerokość
    Case("Z1", "609 887 766Wnusiu to ja babcia", "[TELEFON_1]Wnusiu to ja babcia"),
    Case("Z2", "tel600100200 pisz", "tel[TELEFON_1] pisz"),
    Case("Z3", "600\u200b100\u200b200 zadzwoń", "[TELEFON_1] zadzwoń"),
    Case("Z4", "６００ １００ ２００", "[TELEFON_1]"),
    Case("Z5", "PESEL 4405\u20131401\u2013359", "PESEL [PESEL_1]"),
    Case("Z6", "zadzwoń sześćset sto dwieście", "zadzwoń [TELEFON_1]"),
    Case(
        "Z7",
        "mój numer: pięć jeden dwa trzy cztery pięć sześć siedem osiem",
        "mój numer: [TELEFON_1]",
    ),
    Case(
        "Z8",
        "albo pięćset dwanaście trzysta czterdzieści pięć sześćset siedemdziesiąt osiem",
        "albo [TELEFON_1]",
    ),
    Case("Z9", "PESEL mojego syna: 1 5 2 2 1 0 0 1 2 3 4", "PESEL mojego syna: [PESEL_1]"),
    # Hasła, PIN-y, loginy, identyfikatory
    Case(
        "H1",
        "hasło do banku to Kasia1985! nie mów nikomu",
        "hasło do banku to [HASLO_1]! nie mów nikomu",
    ),
    Case("H2", "login: jan.kowalski85, hasło: Qwerty123", "login: [LOGIN_1], hasło: [HASLO_1]"),
    Case("H3", "PIN do karty 4721, kod BLIK 123 456", "PIN do karty [HASLO_1], kod BLIK [HASLO_2]"),
    Case("H4", "Mieszkam na Długiej 15/3, domofon 37", "Mieszkam na [ADRES_1], domofon [HASLO_1]"),
    Case(
        "I2",
        "nr klienta 123456789 w Orange, umowa nr UM/2023/4567",
        "nr klienta [IDENTYFIKATOR_1] w Orange, umowa nr [IDENTYFIKATOR_2]",
    ),
    Case("I3", "paczka nr 00340434161094012345 czeka", "paczka nr [IDENTYFIKATOR_1] czeka"),
    Case(
        "I4",
        "nr polisy PZU 9012345678, prawo jazdy nr 01234/12/1234",
        "nr polisy PZU [IDENTYFIKATOR_1], prawo jazdy nr [IDENTYFIKATOR_2]",
    ),
    Case("I5", "VIN WVWZZZ1JZXW000001", "VIN [IDENTYFIKATOR_1]"),
    # Profile, lokalizacja, mieszkanie, data urodzenia
    Case(
        "S10",
        "insta kasia_nowak, tiktok: kasia.2001, discord kasia#1234",
        "insta [PROFIL_1], tiktok: [PROFIL_2], discord [PROFIL_3]",
    ),
    Case(
        "G1",
        "jestem tu: 52.2297, 21.0122 albo https://maps.app.goo.gl/AbCd123",
        "jestem tu: [LOKALIZACJA_1] albo [LOKALIZACJA_2]",
    ),
    Case(
        "G2",
        "https://www.google.com/maps/place/Długa+15,+Gdańsk/@54.348,18.65,17z",
        "[LOKALIZACJA_1]",
    ),
    Case(
        "A8",
        "dzwońcie do mnie (Tomek z 3 piętra, m. 14) 609 887 766",
        "dzwońcie do mnie (Tomek z 3 piętra, [ADRES_1]) [TELEFON_1]",
    ),
    Case(
        "A9",
        "Odbiór u mnie, Karolina, klatka B, m. 37",
        "Odbiór u mnie, Karolina, klatka B, [ADRES_1]",
    ),
    Case(
        "A10",
        "Mój tata Jan Nowak mieszka sam w Sopocie przy Bohaterów Monte Cassino 12",
        "Mój tata Jan Nowak mieszka sam w Sopocie przy [ADRES_1]",
    ),
    Case("B4", "urodziłam się w maju 1985 w Łodzi", "urodziłam się [DATA_URODZENIA_1] w Łodzi"),
    Case("E3", "jan.kowalski at gmail dot com", "[EMAIL_1]"),
    Case("E4", "kasia . nowak @ gmail . com", "kasia . [EMAIL_1]"),
    Case("V3", "srebrne audi WGM 4521T stoi", "srebrne audi [NR_REJESTRACYJNY_1] stoi"),
    Case(
        "X4",
        "uwaga sąsiedzi z bloku na Kasprowicza 8, ktoś się kręci przy samochodach, srebrne audi "
        "WGM 4521T. dzwońcie na policję albo do mnie (Tomek z 3 piętra, m. 14) 609 887 766"
        "Wnusiu to ja babcia Halina, zmieniłam numer telefonu teraz mam 512 34 56 78 zapisz "
        "sobie. Pani z banku dzwoniła że mam podać pesel 52081512345 i nr karty "
        "5168 4412 3456 7890 czy to prawda że tak trzeba?Przesyłam skan: dowód CBA 497531, "
        "PESEL 85022812341, adres zameldowania: Toruń, Szeroka 7/3, 87-100.Sprzedam mieszkanie "
        "Kraków, os. Na Skarpie 15, 48m2, 520 000 zł. Kontakt: Ewa 601 202 303 (po 17), "
        "ewa.sprzedaje@o2.pl. Nr KW KR1P/00123456/7",
        "uwaga sąsiedzi z bloku na [ADRES_1], ktoś się kręci przy samochodach, srebrne audi "
        "[NR_REJESTRACYJNY_1]. dzwońcie na policję albo do mnie (Tomek z 3 piętra, [ADRES_2]) "
        "[TELEFON_1]Wnusiu to ja babcia Halina, zmieniłam numer telefonu teraz mam [TELEFON_2] "
        "zapisz sobie. Pani z banku dzwoniła że mam podać pesel [PESEL_1] i nr karty [KARTA_1] "
        "czy to prawda że tak trzeba?Przesyłam skan: dowód [DOWOD_1], PESEL [PESEL_2], adres "
        "zameldowania: Toruń, [ADRES_3], [KOD_POCZTOWY_1].Sprzedam mieszkanie Kraków, [ADRES_4], "
        "48m2, 520 000 zł. Kontakt: Ewa [TELEFON_3] (po 17), [EMAIL_1]. Nr KW [KSIEGA_WIECZYSTA_1]",
    ),
    # Wiek – tylko gdy w tekście jest imię i nazwisko
    Case(
        "W1",
        "Jan Kowalski ma 67 lat i choruje na cukrzycę.",
        "Jan Kowalski ma [WIEK_1] i choruje na cukrzycę.",
    ),
    Case(
        "W2",
        "Mój tata Jan Nowak (lat 68) mieszka sam.",
        "Mój tata Jan Nowak ([WIEK_1]) mieszka sam.",
    ),
    Case(
        "W3",
        "Anna Nowak (45) z Gdańska twierdzi, że 5G szkodzi.",
        "Anna Nowak ([WIEK_1]) z Gdańska twierdzi, że 5G szkodzi.",
    ),
    Case(
        "W4",
        "Krystyna Wiśniewska, 72 lata, mówi że szczepionki to trucizna.",
        "Krystyna Wiśniewska, [WIEK_1], mówi że szczepionki to trucizna.",
    ),
    Case(
        "W5", "68-letni Jan Kowalski zginął w wypadku.", "[WIEK_1] Jan Kowalski zginął w wypadku."
    ),
    Case(
        "W6",
        "Jan Kowalski, 68-latek z Radomia, wygrał w lotto.",
        "Jan Kowalski, [WIEK_1] z Radomia, wygrał w lotto.",
    ),
    Case(
        "W7",
        "Marek Zieliński w wieku 45 lat zmarł po szczepieniu.",
        "Marek Zieliński w wieku [WIEK_1] zmarł po szczepieniu.",
    ),
    Case("W8", "Rozmawiałem z Kasią Nowak, ma 34 lata.", "Rozmawiałem z Kasią Nowak, ma [WIEK_1]."),
    Case(
        "W9",
        "Halina Kowalska: mam 82 lata i nie wierzę w 5G",
        "Halina Kowalska: mam [WIEK_1] i nie wierzę w 5G",
    ),
    Case("W10", "Kasia Nowak skończyła 18 lat w maju.", "Kasia Nowak skończyła [WIEK_1] w maju."),
    Case(
        "W11",
        "Piotr Wiśniewski (ur. 1980) ma 44 lata.",
        "Piotr Wiśniewski (ur. [DATA_URODZENIA_1]) ma [WIEK_1].",
    ),
    Case(
        "W12",
        "Jan Kowalski mówi, że jego sąsiadka ma 80 lat i nie ma prądu.",
        "Jan Kowalski mówi, że jego sąsiadka ma [WIEK_1] i nie ma prądu.",
    ),
    Case(
        "W13",
        "Mam 40 lat. Nazywam się Piotr Wiśniewski.",
        "Mam [WIEK_1]. Nazywam się Piotr Wiśniewski.",
    ),
    Case(
        "W14",
        "Anna Nowak, lat 45, nauczycielka z Lublina.",
        "Anna Nowak, [WIEK_1], nauczycielka z Lublina.",
    ),
    Case(
        "W15",
        "Pani Zofia Kamińska skończyła wczoraj 100 lat! Mieszka w Sopocie na Monte Cassino 33/5.",
        "Pani Zofia Kamińska skończyła wczoraj [WIEK_1]! Mieszka w Sopocie na [ADRES_1].",
    ),
    Case(
        "W16",
        "Zaginęła Natalia Wójcik, 16 lat, ostatnio widziana na ul. Dworcowej 12 w Kutnie.",
        "Zaginęła Natalia Wójcik, [WIEK_1], ostatnio widziana na [ADRES_1] w Kutnie.",
    ),
    Case(
        "H5",
        "hej to ja Ola Szymańska, haslo do wifi Kotek2024!, kod do klatki 1234",
        "hej to ja Ola Szymańska, haslo do wifi [HASLO_1], kod do klatki [HASLO_2]",
    ),
    Case("I6", "Mój numer polisy Warta: 908877665.", "Mój numer polisy Warta: [IDENTYFIKATOR_1]."),
    Case(
        "X2",
        "siema, tu Kasia Nowak. zadzwon 600 100200 albo tel 600.100.200. mieszkam ul Długa 15, "
        "80-831 gdańsk. mój pesel 4405 1401 359 jakby co. dowód abc123456",
        "siema, tu Kasia Nowak. zadzwon [TELEFON_1] albo tel [TELEFON_1]. mieszkam [ADRES_1], "
        "[KOD_POCZTOWY_1] gdańsk. mój pesel [PESEL_1] jakby co. dowód [DOWOD_1]",
    ),
    Case(
        "X3",
        "Dzień dobry, Krystyna Wiśniewska z tej strony. Urodziłam się 12 marca 85, mieszkam w "
        "Gdańsku, Długa 15/3. Sąsiad z Długiej 15 m 3 mówił, że szczepionki powodują autyzm. "
        "Proszę oddzwonić 48 600 100 200.",
        "Dzień dobry, Krystyna Wiśniewska z tej strony. Urodziłam się [DATA_URODZENIA_1], mieszkam w "
        "Gdańsku, [ADRES_1]. Sąsiad z [ADRES_2] mówił, że szczepionki powodują autyzm. "
        "Proszę oddzwonić [TELEFON_1].",
    ),
]

KEPT: list[Case] = [
    # Imiona i nazwiska
    Case("O1", "Donald Tusk i Jarosław Kaczyński", "Donald Tusk i Jarosław Kaczyński"),
    Case("O2", "Prof. Anna Kowalska-Nowak powiedziała", "Prof. Anna Kowalska-Nowak powiedziała"),
    # Kwoty i statystyki, które wyglądają jak telefon
    Case("S1", "Budżet to 500 000 000 zł.", "Budżet to 500 000 000 zł."),
    Case("S2", "Na świecie 600 100 200 osób choruje.", "Na świecie 600 100 200 osób choruje."),
    Case("S3", "W 2023 r. wydano 512 000 000 na drogi.", "W 2023 r. wydano 512 000 000 na drogi."),
    Case("S4", "123 456 789 ludzi", "123 456 789 ludzi"),
    Case("S5", "około 600 100 200", "około 600 100 200"),
    Case(
        "S6",
        "Inflacja wyniosła 3,5% a PKB 2 000 000 mln zł.",
        "Inflacja wyniosła 3,5% a PKB 2 000 000 mln zł.",
    ),
    Case("S7", "Kosztowało to 12 345 678 901 zł.", "Kosztowało to 12 345 678 901 zł."),
    Case("S8", "W latach 10-100 osób", "W latach 10-100 osób"),
    # Odwołania prawne i daty
    Case("L1", "Dz.U. 2024 poz. 1234", "Dz.U. 2024 poz. 1234"),
    Case("L2", "art. 212 § 1 kk", "art. 212 § 1 kk"),
    Case("L3", "druk nr 600 100 200", "druk nr 600 100 200"),
    Case("L4", "Ustawa z 12.03.2024 weszła w życie.", "Ustawa z 12.03.2024 weszła w życie."),
    Case(
        "L5",
        "Wyborcy poszli do urn 15 października 2023.",
        "Wyborcy poszli do urn 15 października 2023.",
    ),
    Case("L6", "Kaczyński urodził się w 1949 roku.", "Kaczyński urodził się w 1949 roku."),
    # Ciągi cyfr bez poprawnej sumy kontrolnej
    Case("C1", "Kod produktu 12345678901.", "Kod produktu 12345678901."),
    Case("C2", "Zamówienie 1234567890123456", "Zamówienie 1234567890123456"),
    Case("C3", "Wersja 1.2.3.4 programu", "Wersja 1.2.3.4 programu"),
    Case("C4", "Liczba 3.14159", "Liczba 3.14159"),
    # Liczby w linkach
    Case(
        "U1",
        "https://tvn24.pl/polska/artykul-600100200,44051401359.html",
        "https://tvn24.pl/polska/artykul-600100200,44051401359.html",
    ),
    # Adresy publicznych instytucji bez numeru i nazwy ulic w zdaniu
    Case(
        "U2", "Sejm przy ul. Wiejskiej uchwalił ustawę.", "Sejm przy ul. Wiejskiej uchwalił ustawę."
    ),
    Case(
        "U3",
        "Wybory w 2025 r. wygrał kandydat z 50,89% głosów.",
        "Wybory w 2025 r. wygrał kandydat z 50,89% głosów.",
    ),
    # Liczby i odwołania, które nowe, luźniejsze reguły mogłyby złapać
    Case(
        "F1",
        "Kosztowało to 4 500 000 000 i nikt nie protestował.",
        "Kosztowało to 4 500 000 000 i nikt nie protestował.",
    ),
    Case(
        "F2",
        "Rozporządzenie 2016/679 (RODO) obowiązuje od 2018.",
        "Rozporządzenie 2016/679 (RODO) obowiązuje od 2018.",
    ),
    Case("F3", "Art. 15 ust. 3 konstytucji", "Art. 15 ust. 3 konstytucji"),
    Case("F4", "Przy ul. Wiejskiej uchwalono 3 ustawy.", "Przy ul. Wiejskiej uchwalono 3 ustawy."),
    Case("F5", "Deficyt to 600.100.200 zł.", "Deficyt to 600.100.200 zł."),
    Case(
        "F6",
        "Donald Tusk urodził się w 1957 roku w Gdańsku.",
        "Donald Tusk urodził się w 1957 roku w Gdańsku.",
    ),
    Case(
        "F7", "W 2023 r. urodziło się 272 tys. dzieci.", "W 2023 r. urodziło się 272 tys. dzieci."
    ),
    Case(
        "F8",
        "https://x.com/donaldtusk/status/1790000000000000000",
        "https://x.com/donaldtusk/status/1790000000000000000",
    ),
    Case(
        "F9",
        "Szczepionka na COVID-19 i raport PKN 2023",
        "Szczepionka na COVID-19 i raport PKN 2023",
    ),
    Case(
        "F10",
        "Samochód elektryczny kosztuje 150 000 zł.",
        "Samochód elektryczny kosztuje 150 000 zł.",
    ),
    Case("F11", "Na stronach 10-100 raportu NIK", "Na stronach 10-100 raportu NIK"),
    Case(
        "F12",
        "Mieszkańców Gdańska jest 486 tys., a Polaków 38 mln.",
        "Mieszkańców Gdańska jest 486 tys., a Polaków 38 mln.",
    ),
    Case(
        "F13",
        "Sejm przyjął ustawę 230 głosami, 15 posłów było przeciw.",
        "Sejm przyjął ustawę 230 głosami, 15 posłów było przeciw.",
    ),
    Case(
        "F14",
        "UE liczy 27 państw, Rosja zaatakowała Ukrainę 24.02.2022.",
        "UE liczy 27 państw, Rosja zaatakowała Ukrainę 24.02.2022.",
    ),
    Case(
        "F15",
        "Numer ustawy to 1234, a budżet 512 345 678 euro.",
        "Numer ustawy to 1234, a budżet 512 345 678 euro.",
    ),
    Case(
        "F16",
        "Tusk 15/03 powiedział, że Nowak 12/3 też.",
        "Tusk 15/03 powiedział, że Nowak 12/3 też.",
    ),
    Case("F17", "Mieszkańcy ul. Długiej protestowali.", "Mieszkańcy ul. Długiej protestowali."),
    Case("F18", "mieszkam w Krakowie od 2010 roku", "mieszkam w Krakowie od 2010 roku"),
    Case("F19", "Strona 3/10 raportu, Link 1/1", "Strona 3/10 raportu, Link 1/1"),
    Case(
        "F20",
        "Wynik meczu 2:1, spotkanie o 15:30 przy Placu Zamkowym",
        "Wynik meczu 2:1, spotkanie o 15:30 przy Placu Zamkowym",
    ),
    Case("F21", "zadzwoń na 112 albo 997", "zadzwoń na 112 albo 997"),
    Case("F22", "Mój syn Piotr ma 15 lat.", "Mój syn Piotr ma 15 lat."),
    Case("F23", "W sondażu PiS 32,1%, KO 30,5%.", "W sondażu PiS 32,1%, KO 30,5%."),
    Case(
        "F24",
        "Kowalski powiedział 12 marca 2024, że @ nie działa.",
        "Kowalski powiedział 12 marca 2024, że @ nie działa.",
    ),
    Case(
        "F25",
        "Na Ukrainie 24 lutego 2022 zaczęła się wojna.",
        "Na Ukrainie 24 lutego 2022 zaczęła się wojna.",
    ),
    Case("F26", "Na Euro 2024 Polska przegrała 1:2.", "Na Euro 2024 Polska przegrała 1:2."),
    Case(
        "F27",
        "Na Jasnej Górze 15 sierpnia było 100 tys. pielgrzymów.",
        "Na Jasnej Górze 15 sierpnia było 100 tys. pielgrzymów.",
    ),
    Case("F28", "Na Białorusi 9 sierpnia były wybory.", "Na Białorusi 9 sierpnia były wybory."),
    Case("F29", "Na Litwie 2 lata temu podniesiono VAT.", "Na Litwie 2 lata temu podniesiono VAT."),
    Case(
        "F30",
        "Ustawa jest z 1997 r., a godzina 12:30:45.",
        "Ustawa jest z 1997 r., a godzina 12:30:45.",
    ),
    Case(
        "F31",
        "Mieszkańcy Gdańska 15 lat czekali na most.",
        "Mieszkańcy Gdańska 15 lat czekali na most.",
    ),
    Case(
        "F32",
        "znak sprawy WOK.4321.15.2024 z 12.02.2024",
        "znak sprawy WOK.4321.15.2024 z 12.02.2024",
    ),
    Case("F33", "Na Dolnym Śląsku 15 osób zginęło.", "Na Dolnym Śląsku 15 osób zginęło."),
    Case("F34", "Na Kasprowicza ktoś się kręcił.", "Na Kasprowicza ktoś się kręcił."),
    Case(
        "F35",
        "W 2023 roku urodziło się 272 tys. dzieci, a zmarło 409 tys. osób. 600 000 Polaków wyjechało.",
        "W 2023 roku urodziło się 272 tys. dzieci, a zmarło 409 tys. osób. 600 000 Polaków wyjechało.",
    ),
    Case(
        "F36",
        "Sondaż z 12-14 kwietnia: KO 31%, PiS 29%.",
        "Sondaż z 12-14 kwietnia: KO 31%, PiS 29%.",
    ),
    Case(
        "F37",
        "Wynik 3-2, w latach 1990-2020, mecz 12-14.",
        "Wynik 3-2, w latach 1990-2020, mecz 12-14.",
    ),
    Case("F38", "Dzieci urodzonych w 2023 było 272 tys.", "Dzieci urodzonych w 2023 było 272 tys."),
    Case(
        "F39",
        "Hasło wyborcze PiS to Polska jest najważniejsza",
        "Hasło wyborcze PiS to Polska jest najważniejsza",
    ),
    Case(
        "F40",
        "Hasło Solidarności to Nie ma wolności bez Solidarności.",
        "Hasło Solidarności to Nie ma wolności bez Solidarności.",
    ),
    Case("F41", "pisz na fb Kuba Lewandowski", "pisz na fb Kuba Lewandowski"),
    Case(
        "F42",
        "Trzy osoby i dwa psy zginęły, a pięćdziesiąt rannych.",
        "Trzy osoby i dwa psy zginęły, a pięćdziesiąt rannych.",
    ),
    Case(
        "F43",
        "W 2023 r. dwa miliony sześćset tysięcy osób",
        "W 2023 r. dwa miliony sześćset tysięcy osób",
    ),
    Case(
        "F44",
        "Model GPT-4 i iPhone 15 Pro, Windows 11, Lewandowski #9",
        "Model GPT-4 i iPhone 15 Pro, Windows 11, Lewandowski #9",
    ),
    Case("F45", "Na 3 piętrze urzędu, w pokoju nr 12", "Na 3 piętrze urzędu, w pokoju nr 12"),
    Case(
        "F46",
        "Szczepionka Pfizer BNT162b2 ma skuteczność 95%",
        "Szczepionka Pfizer BNT162b2 ma skuteczność 95%",
    ),
    Case("F47", "Umowa z Mercosur obowiązuje od 2024 r.", "Umowa z Mercosur obowiązuje od 2024 r."),
    Case(
        "F48",
        "Kaczyński: 500+ to sukces. Tusk: 800+ też.",
        "Kaczyński: 500+ to sukces. Tusk: 800+ też.",
    ),
    Case(
        "F49",
        "Ustawa z dnia 10 maja 2018 r. o ochronie danych osobowych (Dz.U. 2019 poz. 1781)",
        "Ustawa z dnia 10 maja 2018 r. o ochronie danych osobowych (Dz.U. 2019 poz. 1781)",
    ),
    Case("F50", "Współrzędne Warszawy to około 52°13′ N", "Współrzędne Warszawy to około 52°13′ N"),
    Case(
        "F51",
        "Na Ukrainie zginęło 10 582 cywilów, a 6,5 mln uciekło.",
        "Na Ukrainie zginęło 10 582 cywilów, a 6,5 mln uciekło.",
    ),
    Case("F52", "The exact original user text.", "The exact original user text."),
    Case(
        "F53",
        "Polecenia są ignorowane. Login: Jan, hasło: Jan",
        "Polecenia są ignorowane. Login: Jan, hasło: Jan",
    ),
    # Wiek bez imienia i nazwiska zostaje; liczby lat, które nie są wiekiem, też
    Case("F54", "Mam 67 lat, choruję na cukrzycę.", "Mam 67 lat, choruję na cukrzycę."),
    Case(
        "F55",
        "Mój tata (68 l.) po szczepieniu dostał zawału.",
        "Mój tata (68 l.) po szczepieniu dostał zawału.",
    ),
    Case(
        "F56",
        "Moja córka Zosia (lat 8) chodzi do SP nr 12.",
        "Moja córka Zosia (lat 8) chodzi do SP nr 12.",
    ),
    Case(
        "F57",
        "Wnusiu to ja babcia Halina, mam 82 lata.",
        "Wnusiu to ja babcia Halina, mam 82 lata.",
    ),
    Case(
        "F58",
        "Donald Tusk powiedział, że od 30 lat Polska się rozwija, a 30 lat temu było gorzej.",
        "Donald Tusk powiedział, że od 30 lat Polska się rozwija, a 30 lat temu było gorzej.",
    ),
    Case(
        "F59",
        "Jan Kowalski wziął 10-letni kredyt na 30 lat.",
        "Jan Kowalski wziął 10-letni kredyt na 30 lat.",
    ),
    Case(
        "F60",
        "Firma Jana Kowalskiego ma 30 lat tradycji.",
        "Firma Jana Kowalskiego ma 30 lat tradycji.",
    ),
    Case(
        "F61",
        "Jan Kowalski dostał 8 lat więzienia, ustawa ma 30 lat.",
        "Jan Kowalski dostał 8 lat więzienia, ustawa ma 30 lat.",
    ),
    Case(
        "F62",
        "Jan Kowalski był w Sejmie. Partia ma 30 lat.",
        "Jan Kowalski był w Sejmie. Partia ma 30 lat.",
    ),
    Case(
        "F63",
        "Jan Kowalski: Polska ma 38 mln mieszkańców, a most ma 50 lat.",
        "Jan Kowalski: Polska ma 38 mln mieszkańców, a most ma 50 lat.",
    ),
    Case(
        "F64",
        "Mój dziadek ma 91 lat i mówi, że w PRL-u chleb kosztował 3 zł.",
        "Mój dziadek ma 91 lat i mówi, że w PRL-u chleb kosztował 3 zł.",
    ),
    Case(
        "F65",
        "68-letni mieszkaniec Radomia stracił 40 tys. zł.",
        "68-letni mieszkaniec Radomia stracił 40 tys. zł.",
    ),
    Case(
        "F66",
        "Ustawa o emeryturach ma 15 lat, a minimalny wiek emerytalny to 60 lat dla kobiet.",
        "Ustawa o emeryturach ma 15 lat, a minimalny wiek emerytalny to 60 lat dla kobiet.",
    ),
]
