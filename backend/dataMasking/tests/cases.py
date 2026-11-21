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
]
