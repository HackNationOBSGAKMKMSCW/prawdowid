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
    Case("P2", "Urodzona w 2002: 02270803624", "Urodzona w 2002: [PESEL_1]"),
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
]
