"""Reguły wykrywania danych osobowych w polskim tekście.

Każda reguła to wzorzec i opcjonalnie: walidator sumy kontrolnej, słowo-klucz
szukane w pobliżu wartości oraz flaga ``weak``. Reguły ``weak`` (sam kształt,
bez sumy kontrolnej, np. telefon) nie maskują liczb, po których stoi jednostka
(„500 000 000 zł”), które są częścią większej liczby („4 500 000 000”) ani przed
którymi stoi odwołanie prawne („poz. 1234”).

Reguły są pisane pod naturalne wiadomości: bez kropek w skrótach („ul Długa”),
małymi literami, z dowolnymi separatorami w numerach („600.100.200”, „4405 1401 359”).
Litery O w numerach („6OO 1OO 2OO”) masker zamienia na zera przed dopasowaniem.

Imion i nazwisk celowo nie wykrywamy: zostają w tekście.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from . import validators as v


class Keyword(Enum):
    NONE = "none"
    """Słowo-klucz nie ma znaczenia."""
    REQUIRED = "required"
    """Bez słowa-klucza w pobliżu reguła nic nie maskuje."""
    BYPASS = "bypass"
    """Słowo-klucz przed wartością pomija walidację (użytkownik sam nazwał dane)."""


@dataclass(frozen=True)
class Rule:
    label: str
    pattern: re.Pattern[str]
    priority: int
    validate: Callable[[str], bool] | None = None
    keyword: re.Pattern[str] | None = None
    keyword_mode: Keyword = Keyword.NONE
    keyword_after: bool = False
    """Szukaj słowa-klucza także za wartością („WA12345 to moje auto”)."""
    weak: bool = False
    reject: re.Pattern[str] | None = None
    """Wartość pasująca w całości do tego wzorca to co innego (np. telefon „48 600 100 200”)."""
    requires_full_name: bool = False
    """Maskuj tylko, gdy w tekście jest imię i nazwisko (np. wiek – sam nikogo nie wskazuje)."""
    inside_urls: bool = False
    """Maskuj też w linkach (e-mail, profil); domyślnie liczby w linkach zostają."""
    blocked_after: re.Pattern[str] | None = None
    """Nie maskuj, jeśli wartość stoi zaraz po tym tekście (np. „wersja 1.2.3.4”)."""


# Granice liczby: nie doklejona do liter/cyfr i nie będąca częścią ułamka („3,5”, „1.25”).
_B = r"(?<!\w)(?<!\d[.,])"
_E = r"(?!\w)(?![.,]\d)"
# Granice liczby z separatorami: nie kawałek dłuższego ciągu grup („4 500 000 000”).
_BS = r"(?<!\w)(?<!\d[.,])(?<!\d[ .\-])"
_ES = r"(?!\w)(?![.,]\d)(?![ .\-]\d)"
# Dowolny pojedynczy separator między cyframi.
_S = r"[ .\-]?"

_UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"
_LOWER = "a-ząćęłńóśźż"
_MONTHS = (
    "stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|"
    "września|wrzesnia|października|pazdziernika|listopada|grudnia"
)
_PERSON_NOUNS = (
    r"mężczyzn\w*|mezczyzn\w*|kobiet\w*|chłop\w*|chlop\w*|dziewczyn\w*|dziewczyn\w*|syn\w*|"
    r"córk\w*|cork\w*|dziec\w*|senior\w*|seniork\w*|emeryt\w*|pacjent\w*|kierowc\w*|"
    r"mieszkan\w*|ojc\w*|ojciec|matk\w*|brat\w*|siostr\w*|wnu\w*|bab\w*|dziad\w*|"
    r"uczni\w*|uczeń|uczen|student\w*|nastolat\w*|chłopiec|chlopiec|mąż|maz|męża|meza|żon\w*|"
    r"zon\w*|sąsiad\w*|sasiad\w*|pan\w*|osob\w*|poszkodowan\w*|zmarł\w*|zmarl\w*|"
    r"sprawc\w*|ofiar\w*|polityk\w*|posł\w*|posel|radn\w*|lekarz\w*|aktor\w*|piosenkar\w*|"
    r"kolega|koleg\w*|koleżank\w*|kolezank\w*|przyjaciel\w*|przyjaciół\w*|znajom\w*|szef\w*|"
    r"tata|taty|tato|mama|mamy|mamą|babcia|babci|dziadek|dziadka|ciocia|cioci|wujek|wujka|"
    r"teściow\w*|tesciow\w*|szwagier\w*|szwagr\w*|bratow\w*|kuzyn\w*|partner\w*|"
    r"chłopak\w*|chlopak\w*|narzeczon\w*"
)
_AGE_ADVERB = (
    r"(?:(?i:już|juz|dopiero|prawie|ponad|niecałe|niecale|około|okolo|skończone|skonczone|"
    r"równo|rowno|dokładnie|dokladnie)\s+)?"
)
# Liczba lat osoby; „30 lat tradycji/stażu/więzienia” to nie wiek.
_AGE = (
    r"\d{1,3}\s*(?i:lat|lata|latek|l\.|wiosen|rok|roku|miesięcy|miesiecy|miesiące|miesiace|"
    r"tygodni|urodziny)(?!\w)(?!\s+(?i:tradycji|stażu|stazu|doświadczeni\w*|doswiadczeni\w*|"
    r"histori\w*|istnieni\w*|działalności|dzialalnosci|pracy|służby|sluzby|temu|gwarancji|"
    r"kadencji|kredytu|umowy|więzienia|wiezienia|odsiadki|wyroku|ważności|waznosci))"
    r"|\d{1,3}(?=\s*(?:[,.;!?)]|$))"
)
# „w maju 1985”
_MONTHS_IN = (
    "styczniu|lutym|marcu|kwietniu|maju|czerwcu|lipcu|sierpniu|wrześniu|wrzesniu|"
    "październiku|pazdzierniku|listopadzie|grudniu"
)
_NUMBER_WORDS = (
    r"(?:jeden|jedna|dwa|dwie|trzy|cztery|pięć|piec|sześć|szesc|siedem|osiem|dziewięć|dziewiec|"
    r"dziesięć|dziesiec|\w+naście|\w+nascie|dwadzieścia|dwadziescia|trzydzieści|trzydziesci|"
    r"czterdzieści|czterdziesci|\w+dziesiąt|\w+dziesiat|sto)"
    r"(?:\s+(?:jeden|dwa|trzy|cztery|pięć|piec|sześć|szesc|siedem|osiem|dziewięć|dziewiec))?"
)

# Słowa, po których „Wyraz 15/3” to odwołanie prawne albo dokument, a nie adres.
_NOT_STREET = (
    r"(?!(?i:art|dz|poz|ust|nr|druk|sygn|rozdz\w*|uchwał\w*|ustaw\w*|wyrok\w*|rok\w*|tom\w*|"
    r"str|strona|stron\w*|rozporządz\w*|rozporzadz\w*|dyrektyw\w*|kodeks\w*|pkt|par|covid|"
    r"decyzj\w*|sprawa|sprawie|akt|aktu|załącznik\w*|zalacznik\w*|tabel\w*|rys\w*|wykres\w*|"
    r"punkt\w*|pozycj\w*|godz\w*|numer\w*|kategori\w*|klas\w*|wiek\w*|gr|grupa|etap\w*|"
    r"link\w*|część|czesc|cz|pytani\w*|krok\w*|odcin\w*|odc|slajd\w*|wynik\w*|ocen\w*|mecz\w*|"
    r"rund\w*|sezon\w*|wątek|watek|post\w*|wpis\w*|zdjęci\w*|zdjec\w*|foto|wersj\w*|edycj\w*|"
    r"zadani\w*|ćwiczeni\w*|cwiczeni\w*|lekcj\w*|rozdział\w*|część\w*|tydzień|tydzien|dzień|dzien|"
    r"miesiąc\w*|miesiac\w*|kwartał\w*|kwartal\w*|ue|rodo|wa|pis|ko|psl)\b)"
)
# Słowo nazwy ulicy: od wielkiej litery, same litery („Długa”, „Kościuszki”, „Curie-Skłodowskiej”).
_WORD = rf"[{_UPPER}][{_LOWER}{_UPPER}'\-]*[{_LOWER}{_UPPER}]\.?"
# Nazwa ulicy od wielkiej litery: 1–4 słowa, liczba („3 Maja”) albo skrót („gen.”, „Jana Pawła II”).
_STREET_CAP = (
    rf"{_NOT_STREET}(?:{_WORD}|\d{{1,2}}|(?i:gen|ks|św|sw|marsz|prof|kard|bpa?|al)\.)"
    rf"(?:\s+(?:{_WORD}|(?i:gen|ks|św|sw|marsz|prof|kard|bpa?)\.|[IVX]+)){{0,3}}"
)
# Po słowie „ulica”/„ul” nazwa bywa pisana małą literą: jedno słowo („ul długa 15”).
_STREET_ANY = rf"(?:{_STREET_CAP}|[{_LOWER}][{_LOWER}\-]{{2,}})"
_FLAT = r"(?:\s?/\s?\d{1,4}[a-zA-Z]?|\s?(?i:m\.?|lok\.?|lokal|mieszk\.?|mieszkania)\s?\d{1,4})"
# Bez słowa-klucza: pierwsze słowo musi wyglądać jak ulica („Długa”, „Długiej”, „Kościuszki”),
# a nie jak nazwisko („Tusk 15/3”); numer bez zera z przodu („15/03” to data).
_LOOKS_LIKE_STREET = rf"(?=(?:\d{{1,2}}\s+)?[{_UPPER}][{_LOWER}{_UPPER}'\-]*(?:[aeiouyąęó]|ej|ów|ow|ych|ich)(?![\w]))"
# Po „na” miejscownik krajów („na Ukrainie”, „na Litwie”) kończy się na -e/-i/-u,
# a ulice to dopełniacz albo -ej („na Kasprowicza”, „na Wolskiej”, „na Słowackiego”).
_LOOKS_LIKE_STREET_AFTER_NA = (
    rf"(?=(?:\d{{1,2}}\s+)?[{_UPPER}][{_LOWER}{_UPPER}'\-]*(?:ej|a|ego|ki|ów|ow|ich|ych)(?![\w]))"
)
_FLAT_STRICT = r"(?:\s?/\s?[1-9]\d{0,3}[a-zA-Z]?|\s?(?i:m\.?|lok\.?|lokal|mieszk\.?|mieszkania)\s?[1-9]\d{0,3})"
_HOUSE = rf"\d{{1,4}}[a-zA-Z]?{_FLAT}?(?!\w)(?![.,\-]\d)"
_STREET_KW = (
    r"(?:(?i:ul|os)(?:\.|(?=\s))|(?i:ulic[aąyęe]\w*|al\.|alej[aąię]|aleje|aleja|pl\.|plac(?:u|em)?|"
    r"osiedl(?:e|u|em)))"
)

# Po tym tekst jest kwotą albo statystyką, nie danymi osobowymi.
UNIT_AFTER = re.compile(
    r"\s*(?:zł|zl|złotych|zlotych|pln|eur|euro|usd|dolarów|dolarow|\$|€|%|proc|procent\w*|tys|"
    r"mln|mld|bln|osób|osob|osoby|ludzi|mieszkańców|mieszkancow|polaków|polakow|km|kg|ton|t\b|"
    r"lat|latach|głos\w*|glos\w*|sztuk|szt|m2|m²|ha|razy|dawek|zgonów|zgonow|przypadków|"
    r"przypadkow|metr\w*|minut\w*|godzin\w*|dni|stron\w*|punkt\w*|pkt|posł\w*|posl\w*|państw|"
    r"krajów|dzieci|uczniów|pacjentów|chorych|zakażeń|zakazen|lata|roku|rok|r\.|tygodni\w*|"
    rf"miesięc\w*|miesiac\w*|{_MONTHS})(?!\w)",
    re.IGNORECASE,
)
# Przed tym liczba jest odwołaniem prawnym albo przybliżoną wielkością.
CONTEXT_BEFORE = re.compile(
    r"(?<!\w)(?:poz\.|dz\.\s?u\.?|art\.|nr\s+druku|druk\s+nr|sygn\.?(?:\s+akt)?|ust\.|§|"
    r"ok\.|około|okolo|ponad|prawie|blisko|niemal|nawet|aż|az|stron\w*|str\.)\s*$",
    re.IGNORECASE,
)

URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def _kw(words: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w)(?:{words})", re.IGNORECASE)


def _c(pattern: str, flags: int = 0) -> re.Pattern[str]:
    return re.compile(pattern, flags)


_PHONE_WORDS = _kw(
    r"tel\w*|telefon\w*|kom\.|komórk\w*|komork\w*|numer\w*|nr|dzwo\w*|zadzwo\w*|oddzwo\w*|"
    r"sms\w*|esemes\w*|whatsapp\w*|wapp|kontakt\w*|zadzwoń|dzwoń|pisz\w*"
)
_CAR_WORDS = _kw(
    r"aut[oau]\w*|samoch\w*|pojazd\w*|wozem|wóz|woz|tablic\w*|rejestr\w*|blach\w*|parking\w*|"
    r"zaparkow\w*|parkuj\w*|motor\w*|skuter\w*|ciężarów\w*|ciezarow\w*|bus\w*|furgon\w*|"
    r"jeździ\w*|jezdzi\w*|nr\s+rej|audi|bmw|vw|volkswagen\w*|opel\w*|ford\w*|toyot\w*|"
    r"skod\w*|škod\w*|fiat\w*|renault|peugeot\w*|kia|hyundai\w*|mercedes\w*|seat\w*|"
    r"mazd\w*|hond\w*|nissan\w*|volvo|citroen\w*|citroën\w*|dacia|dacii|tesl\w*|suzuki|"
    r"mitsubishi|lexus\w*|porsche|jeep\w*|mini|cupr\w*|alf\w*\s+romeo|land\s+rover\w*|"
    r"kombi|sedan\w*|hatchback\w*|suv\w*"
)
_MOBILE = rf"[4-8]\d{{2}}(?:{_S}\d){{6}}"
_LANDLINE = rf"\(?[1-9]\d\)?{_S}\d{{3}}{_S}\d{{2}}{_S}\d{{2}}"
# Separatorem w e-mailu zapisanym słownie bywa „małpa”, „(at)”, „[at]”, „kropka”, „(dot)”.
_AT = r"(?:\s*@\s*|\s*[(\[{]\s*(?:at|małpa|malpa)\s*[)\]}]\s*|\s+(?:at|małpa|malpa)\s+)"
_DOT = r"(?:\s?\.\s?|\s*[(\[{]\s*(?:dot|kropka)\s*[)\]}]\s*|\s+(?:dot|kropka)\s+)"
# Przy rozstrzelonym zapisie końcówka domeny musi być prawdziwa, żeby nie łapać zdań.
_TLD = r"(?-i:[a-z]{2}|com|net|org|info|biz|gov|edu|online|app|dev|io|eu)"
_SOCIAL = (
    r"(?:facebook\.com|fb\.com|fb\.me|m\.facebook\.com|instagram\.com|instagr\.am|tiktok\.com|"
    r"twitter\.com|x\.com|linkedin\.com/in|t\.me|youtube\.com|threads\.net|snapchat\.com/add)"
)

RULES: tuple[Rule, ...] = (
    Rule(
        "EMAIL",
        _c(r"(?<![\w.+\-])[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)*\.[A-Za-z]{2,}(?![\w\-])"),
        priority=0,
        inside_urls=True,
    ),
    # E-mail zapisany słownie: „jan małpa gmail kropka com”, „jan(at)gmail.com”.
    Rule(
        "EMAIL",
        _c(
            rf"(?<![\w.+\-])[\w.+\-]+{_AT}[\w\-]+(?:{_DOT}[\w\-]+)*{_DOT}{_TLD}(?![\w\-])",
            re.IGNORECASE,
        ),
        priority=1,
    ),
    # Profil w serwisie społecznościowym (sam profil, bez linków do postów).
    Rule(
        "PROFIL",
        _c(
            rf"(?<![\w/.])(?:https?://)?(?:www\.)?{_SOCIAL}/@?[\w.\-]*[\w\-]"
            r"(?:\?id=\d+)?/?(?![\w/])",
            re.IGNORECASE,
        ),
        priority=0,
        inside_urls=True,
    ),
    Rule(
        "PROFIL",
        _c(
            r"(?<![\w@.\\/])@(?=[A-Za-z0-9_.]*[A-Za-z])[A-Za-z0-9_](?:[A-Za-z0-9_.]{0,28}[A-Za-z0-9_])?"
            r"(?![\w@/])"
        ),
        priority=1,
    ),
    # Numer konta: polski (26 cyfr, opcjonalnie z „PL”) albo zagraniczny IBAN.
    Rule(
        "NR_KONTA",
        _c(
            rf"{_B}(?:PL ?)?\d{{2}}(?:[ \-]?\d{{4}}){{6}}{_E}"
            r"|(?<!\w)[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?(?!\w)",
            re.IGNORECASE,
        ),
        priority=1,
        validate=v.is_iban,
        keyword=_kw(r"kont[oa]|rachun\w*|iban|przelew\w*"),
        keyword_mode=Keyword.BYPASS,
    ),
    Rule(
        "KARTA",
        _c(rf"{_BS}\d(?:[ \-]?\d){{12,18}}{_ES}"),
        priority=2,
        validate=v.is_payment_card,
        keyword=_kw(r"kart\w*|visa|mastercard|maestro|cvv|cvc"),
        keyword_mode=Keyword.BYPASS,
    ),
    # PESEL także z separatorami: „4405 1401 359”, „44-05-14-01359”.
    Rule(
        "PESEL",
        _c(rf"{_BS}\d(?:[ \-]?\d){{10}}{_ES}"),
        priority=3,
        validate=v.is_pesel,
        # „+48 600 100 200” bywa przypadkiem poprawnym PESEL-em.
        reject=re.compile(rf"48{_S}{_MOBILE}|48{_S}{_LANDLINE}"),
        keyword=_kw("pesel"),
        keyword_mode=Keyword.BYPASS,
        weak=True,
    ),
    Rule(
        "NIP",
        _c(
            rf"{_B}(?:PL ?)?\d{{3}}(?P<s>[\- ]?)\d{{3}}(?P=s)\d{{2}}(?P=s)\d{{2}}{_E}"
            rf"|{_B}\d{{3}}-\d{{2}}-\d{{2}}-\d{{3}}{_E}",
            re.IGNORECASE,
        ),
        priority=4,
        validate=v.is_nip,
        keyword=_kw("nip"),
        keyword_mode=Keyword.BYPASS,
        weak=True,
    ),
    Rule(
        "REGON",
        _c(rf"{_B}\d{{14}}{_E}"),
        priority=5,
        validate=v.is_regon,
        keyword=_kw("regon"),
        keyword_mode=Keyword.BYPASS,
    ),
    # 9 cyfr to zwykle telefon, więc 9-cyfrowy REGON tylko po słowie „REGON”.
    Rule(
        "REGON",
        _c(rf"{_B}\d{{9}}{_E}"),
        priority=5,
        keyword=_kw("regon"),
        keyword_mode=Keyword.REQUIRED,
    ),
    Rule(
        "DOWOD",
        _c(r"(?<!\w)[A-Za-z]{3}[ \-]?\d{6}(?!\w)"),
        priority=6,
        validate=v.is_id_card,
        keyword=_kw(r"dow[oó]d\w*|seria|nr\s+dowodu"),
        keyword_mode=Keyword.BYPASS,
    ),
    Rule(
        "PASZPORT",
        _c(r"(?i:paszport\w*|passport)[^\n\d]{0,25}?(?P<v>[A-Za-z]{2} ?\d{7})(?!\w)"),
        priority=6,
    ),
    Rule(
        "DATA_URODZENIA",
        _c(
            r"(?<!\w)(?i:ur(?:\.|(?=\s))|urodz\w*|urodził\w*|urodzil\w*|data\s+urodzenia|d\.\s?ur\.)"
            r"[^\d\n]{0,25}?"
            rf"(?P<v>\d{{1,2}}[./\-]\d{{1,2}}(?:[./\-](?:\d{{4}}|\d{{2}}))?(?![\d.]\d)"
            rf"|\d{{1,2}}\s+(?i:{_MONTHS})(?:\s+'?(?:\d{{4}}|\d{{2}}))?(?!\d)"
            rf"|(?i:w\s+)?(?i:{_MONTHS_IN})\s+'?(?:\d{{4}}|\d{{2}})(?!\d)"
            r"|\d{4}-\d{2}-\d{2})"
        ),
        priority=7,
    ),
    Rule(
        "DATA_URODZENIA",
        _c(r"(?<!\w)(?i:rocznik\w*)\s*'?(?P<v>\d{4}|\d{2})(?!\d)"),
        priority=7,
    ),
    # „(ur. 1971)” – sam rok w notce biograficznej.
    Rule(
        "DATA_URODZENIA",
        _c(
            r"(?<!\w)(?i:ur\.|urodzony|urodzona)\s*(?i:w\s+)?(?P<v>(?:19|20)\d{2})(?!\d)(?![./\-]\d)"
        ),
        priority=7,
    ),
    # „jestem z 1987 r.” – rok urodzenia w pierwszej osobie.
    Rule(
        "DATA_URODZENIA",
        _c(r"(?<!\w)(?i:jestem|jesteśmy|jestesmy)\s+z\s+'?(?P<v>(?:19|20)\d{2}|\d{2})(?!\d)"),
        priority=7,
    ),
    # „ul. Długa 15/3”, „ul długa 15”, „os. Tysiąclecia 45”.
    Rule(
        "ADRES",
        _c(rf"(?<![\w.]){_STREET_KW}\s*{_STREET_ANY}\s+{_HOUSE}"),
        priority=8,
        weak=True,
    ),
    # Po „mieszkam/adres/zameldowany” wystarczy nazwa ulicy, a numer może być słownie.
    Rule(
        "ADRES",
        _c(
            r"(?<!\w)(?i:mieszkam|mieszkasz|mieszka|mieszkamy|mieszkacie|mieszkają|mieszkaja|"
            r"mieszkał\w*|mieszkal\w*|zamieszkał\w*|zamieszkal\w*|zamieszkuj\w*|zam\.|adres\w*|"
            r"meldun\w*|zameldowan\w*|zamelduj\w*)"
            r"(?:[^\n.!?]{0,40}?(?:\s(?i:na|przy)\s+|[:,]\s*)|\s+)"
            rf"(?P<v>{_STREET_KW}\s*{_STREET_ANY}(?:\s+(?:{_HOUSE}|(?i:{_NUMBER_WORDS})(?!\w)))?"
            rf"|{_STREET_CAP}\s+(?:{_HOUSE}|(?i:{_NUMBER_WORDS})(?!\w)))"
        ),
        priority=8,
        weak=True,
    ),
    # Bez słowa-klucza tylko z numerem mieszkania: „Długa 15/3”, „Długiej 15 m 3”.
    Rule(
        "ADRES",
        _c(
            rf"(?<![\w.]){_LOOKS_LIKE_STREET}{_STREET_CAP}\s+[1-9]\d{{0,2}}[a-zA-Z]?{_FLAT_STRICT}"
            r"(?!\w)(?![.,/\-]\d)"
        ),
        priority=8,
        weak=True,
    ),
    # „przy Długiej 5” – adres miejsca (praca, sklep, szkoła).
    Rule(
        "ADRES",
        _c(
            rf"(?<!\w)(?i:przy)\s+(?P<v>{_LOOKS_LIKE_STREET}{_STREET_CAP}\s+[1-9]\d{{0,2}}[a-zA-Z]?"
            rf"{_FLAT_STRICT}?)(?!\w)(?![.,/:\-]\d)"
        ),
        priority=8,
        weak=True,
    ),
    # „na Kasprowicza 8”, „na Wolskiej 23 m 81” – bez nazw krajów („na Ukrainie 24 lutego”).
    Rule(
        "ADRES",
        _c(
            rf"(?<!\w)(?i:na)\s+(?P<v>{_LOOKS_LIKE_STREET_AFTER_NA}{_STREET_CAP}\s+[1-9]\d{{0,2}}"
            rf"[a-zA-Z]?{_FLAT_STRICT}?)(?!\w)(?![.,/:\-]\d)"
        ),
        priority=8,
        weak=True,
    ),
    # Adres zagraniczny: „221B Baker Street”.
    Rule(
        "ADRES",
        _c(
            r"(?<!\w)\d{1,5}[A-Za-z]?\s+(?:[A-Z][a-z]+\s+){1,3}"
            r"(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Lane|Ln\.?|Drive|Dr\.?|Boulevard|Blvd\.?|"
            r"Way|Square|Sq\.?|Place|Court|Ct\.?|Terrace|Close|Crescent|Gardens)(?!\w)"
        ),
        priority=8,
    ),
    # Z prefiksem kraju: pewny telefon. „48 600 100 200” bez plusa też.
    Rule(
        "TELEFON",
        _c(rf"(?:(?<![\w+])(?:\+|00){_S}48|{_BS}48){_S}(?:{_MOBILE}|{_LANDLINE}){_ES}"),
        priority=9,
        weak=True,
    ),
    # Zagraniczny z prefiksem: „+44 7911 123456”, „+49 30 1234 5678”.
    Rule(
        "TELEFON",
        _c(
            r"(?<![\w+])\+(?!48)\d{1,3}[ .\-]?(?:\(\d{1,4}\)[ .\-]?)?\d(?:[ .\-]?\d){6,12}"
            r"(?!\w)(?![.,]\d)"
        ),
        priority=9,
    ),
    # Po „tel.”, „mój nr”, „zadzwoń” numer jest pewny, w dowolnym zapisie.
    Rule(
        "TELEFON",
        _c(rf"{_BS}(?:\+?\d{_S}){{6,11}}\d{_ES}"),
        priority=9,
        keyword=_PHONE_WORDS,
        keyword_mode=Keyword.REQUIRED,
        weak=True,
    ),
    # Komórkowy bez prefiksu: 9 cyfr zaczynających się od 4–8, dowolne separatory.
    Rule(
        "TELEFON",
        _c(rf"{_BS}{_MOBILE}{_ES}"),
        priority=9,
        weak=True,
    ),
    # Stacjonarny: (22) 123 45 67, 22 123 45 67, 22-123-45-67.
    Rule(
        "TELEFON",
        _c(
            rf"{_BS}\(\d{{2}}\) ?\d{{3}}[ .\-]?\d{{2}}[ .\-]?\d{{2}}{_ES}"
            rf"|{_BS}[1-9]\d(?P<s>[ .\-])\d{{3}}(?P=s)\d{{2}}(?P=s)\d{{2}}{_ES}"
        ),
        priority=9,
        weak=True,
    ),
    Rule(
        "IP",
        _c(r"(?<![\w.])\d{1,3}(?:\.\d{1,3}){3}(?!\w)(?!\.\d)"),
        priority=10,
        validate=v.is_ipv4,
        blocked_after=re.compile(r"(?:wersj\w*|ver\.?|v\.?)\s*$", re.IGNORECASE),
    ),
    # Kod pocztowy przed nazwą miejscowości (też małą literą), żeby nie łapać zakresów.
    Rule(
        "KOD_POCZTOWY",
        _c(rf"(?<![\w\-])\d{{2}}-\d{{3}}(?![\w\-])(?=,?\s+[{_UPPER}{_LOWER}]{{3,}})"),
        priority=11,
        weak=True,
    ),
    Rule(
        "KOD_POCZTOWY",
        _c(r"(?i:kod\w*(?:\s+pocztow\w*)?)\W{0,3}(?P<v>\d{2}-?\d{3})(?!\w)"),
        priority=11,
    ),
    Rule(
        "NR_REJESTRACYJNY",
        _c(
            r"(?i:nr\.?\s+rej\w*\.?|numer\w*\s+rejestracyjn\w*|tablic\w*(?:\s+rejestracyjn\w*)?|rejestracj\w*)"
            r"[^\n]{0,15}?(?<!\w)(?P<v>(?=[A-Z]{1,3} ?[A-Z0-9]{0,4}\d)[A-Z]{1,3} ?[A-Z0-9]{4,5})(?!\w)"
        ),
        priority=12,
    ),
    # Polska tablica (pierwsza litera to województwo) tylko przy słowach o aucie.
    Rule(
        "NR_REJESTRACYJNY",
        _c(
            r"(?<!\w)(?=[BCDEFGKLNOPRSTWZ][A-Z]{0,2} ?[A-Z0-9]{0,4}\d)"
            r"[BCDEFGKLNOPRSTWZ][A-Z]{0,2} ?[A-Z0-9]{4,5}(?!\w)"
        ),
        priority=12,
        keyword=_CAR_WORDS,
        keyword_mode=Keyword.REQUIRED,
        keyword_after=True,
    ),
    Rule(
        "MAC",
        _c(r"(?<![\w:\-])[0-9A-Fa-f]{2}([:\-])[0-9A-Fa-f]{2}(?:\1[0-9A-Fa-f]{2}){4}(?![\w:\-])"),
        priority=10,
    ),
    # Numer księgi wieczystej: „KR1P/00123456/7” wskazuje nieruchomość i właściciela.
    Rule(
        "KSIEGA_WIECZYSTA",
        _c(r"(?<!\w)[A-Z]{2}\d[A-Z]/\d{8}/\d(?!\w)", re.IGNORECASE),
        priority=6,
    ),
    # Kod po numerze domu: „Szeroka 7/3, 87-100”.
    Rule(
        "KOD_POCZTOWY",
        _c(r"(?<!\w)\d{1,4}[a-zA-Z]?(?:\s?/\s?\d{1,4})?,\s*(?P<v>\d{2}-\d{3})(?![\w\-])"),
        priority=11,
        weak=True,
    ),
    # Kod po nazwie miejscowości: „Gdynia 81-391”.
    Rule(
        "KOD_POCZTOWY",
        _c(
            rf"(?<!\w){_NOT_STREET}[{_UPPER}][{_LOWER}]+(?:[\s\-][{_UPPER}][{_LOWER}]+)?,?\s+"
            r"(?P<v>\d{2}-\d{3})(?![\w\-])"
        ),
        priority=11,
        weak=True,
    ),
    # Brytyjski kod pocztowy: „NW1 6XE”.
    Rule(
        "KOD_POCZTOWY",
        _c(r"(?<!\w)[A-Z]{1,2}\d[A-Z\d]?\s\d[A-Z]{2}(?!\w)"),
        priority=11,
    ),
    # Hasło, PIN, kod CVV: tylko gdy wygląda jak hasło (cyfra albo znak specjalny),
    # żeby nie łapać „hasła wyborczego”.
    Rule(
        "HASLO",
        _c(
            r"(?<!\w)(?i:hasło|hasla|hasło\s+do\s+\w+|haslo|password|passwd|pass)(?!\w)"
            r"(?:\s+(?i:to|jest|brzmi))?\s*[:=\-]?\s*[\"'„“]?"
            r"(?P<v>[^\s\"'”]{4,40}?)[\"'”]?(?=[\s,;)]|[.!?](?:\s|$)|$)"
        ),
        priority=1,
        validate=v.looks_like_password,
        inside_urls=True,
    ),
    Rule(
        "HASLO",
        _c(
            r"(?<!\w)(?i:pin\w*|kod\s+pin|cvv2?|cvc2?|kod\s+(?:cvv|cvc|blik\w*|dostępu|dostepu|"
            r"weryfikacyjn\w*|sms\w*|autoryzacyjn\w*|do\s+(?:drzwi|bramy|klatki|furtki|domofonu))|"
            r"domofon\w*)(?:\s+(?i:to|do\s+\w+|jest))?\s*[:=\-]?\s*"
            r"(?P<v>\d(?:[ \-]?\d){1,7})(?!\w)"
        ),
        priority=1,
    ),
    Rule(
        "LOGIN",
        _c(
            r"(?<!\w)(?i:login|nazwa\s+użytkownika|nazwa\s+uzytkownika|username|użytkownik|"
            r"uzytkownik|nick\w*)(?!\w)\s*(?i:to|jest)?\s*[:=\-]?\s*@?"
            r"(?P<v>[A-Za-z0-9][\w.\-]{2,40}[A-Za-z0-9_])(?!\w)"
        ),
        priority=1,
        validate=v.looks_like_handle,
    ),
    # Identyfikator klienta, umowy, polisy, paczki, legitymacji, prawa jazdy, VIN.
    Rule(
        "IDENTYFIKATOR",
        _c(
            r"(?<!\w)(?i:(?:nr|numer\w*|id)\.?\s+(?:klienta|umowy|polisy|zamówienia|zamowienia|"
            r"przesyłki|przesylki|paczki|legitymacji|albumu|indeksu|pacjenta|karty\s+pacjenta|"
            r"ubezpieczenia|ubezpieczonego|nadwozia|prawa\s+jazdy|konta\s+klienta|faktury|"
            r"rezerwacji|biletu|zgłoszenia|zgloszenia|sprawy\s+klienta|ewidencyjn\w*|pracownika|"
            r"karty\s+bibliotecznej|karty\s+lojalnościowej|karty\s+lojalnosciowej|vin)|"
            r"(?:paczk\w*|przesyłk\w*|przesylk\w*|polis\w*|umow\w*|legitymacj\w*|prawo\s+jazdy|"
            r"prawa\s+jazdy|vin)\s+(?:nr\.?|numer|o\s+numerze)|vin)"
            r"(?:\s+[A-Z]{2,6}(?=\s))?\s*[:#.\-]?\s*"
            r"(?P<v>(?=[A-Za-z0-9/\-]*\d)[A-Za-z0-9][A-Za-z0-9/\-]{3,39}[A-Za-z0-9])(?!\w)"
        ),
        priority=2,
        weak=True,
    ),
    # Nick po nazwie serwisu: „insta kasia_nowak”, „tiktok: kasia.123”, „discord kasia#1234”.
    Rule(
        "PROFIL",
        _c(
            r"(?<!\w)(?i:insta(?:gram)?|ig|tiktok\w*|tik\s?tok\w*|tt|fb|facebook\w*|snap(?:chat)?\w*|"
            r"discord\w*|telegram\w*|twitter\w*|yt|youtube\w*|twitch\w*|steam\w*|signal\w*|"
            r"threads|bluesky|bsky|reddit\w*|linkedin\w*|gg|gadu)(?!\w)\s*[:\-]?\s*@?"
            r"(?P<v>[A-Za-z0-9_][\w.]{1,30}[A-Za-z0-9_](?:#\d{4})?)(?!\w)"
        ),
        priority=1,
        validate=v.looks_like_handle,
    ),
    Rule(
        "PROFIL",
        _c(r"(?<![\w#])[A-Za-z0-9_.]{2,32}#\d{4}(?!\w)"),
        priority=1,
    ),
    # Położenie: współrzędne GPS i linki do map.
    Rule(
        "LOKALIZACJA",
        _c(r"(?<![\d.])-?\d{1,2}\.\d{4,}\s*[,;]\s*-?\d{1,3}\.\d{4,}(?![\d.])"),
        priority=1,
        inside_urls=True,
    ),
    Rule(
        "LOKALIZACJA",
        _c(
            r"(?<![\w/.])(?:https?://)?(?:www\.)?(?:google\.[a-z.]{2,6}/maps|maps\.google\.[a-z.]{2,6}|"
            r"goo\.gl/maps|maps\.app\.goo\.gl|maps\.apple\.com|openstreetmap\.org|"
            r"waze\.com/ul|what3words\.com|w3w\.co)\S*",
            re.IGNORECASE,
        ),
        priority=0,
        inside_urls=True,
    ),
    Rule(
        "LOKALIZACJA",
        _c(r"(?<!\w)///[a-z]+\.[a-z]+\.[a-z]+(?!\w)"),
        priority=1,
    ),
    # Sam numer mieszkania, gdy z kontekstu wiadomo, że chodzi o mieszkanie.
    Rule(
        "ADRES",
        _c(
            r"(?<!\w)(?:(?i:m\.|lok\.?|lokal\w*|mieszkani[ea]|mieszk\.)|m(?=\s?\d))\s?(?i:nr\.?\s?)?\d{1,4}[a-zA-Z]?(?!\w)"
        ),
        priority=12,
        keyword=_kw(
            r"klatk\w*|piętr\w*|pietr\w*|blok\w*|parter\w*|domofon\w*|u\s+mnie|odbiór|odbior|"
            r"mieszkam|mieszkani\w*|sąsiad\w*|sasiad\w*|kamienic\w*"
        ),
        keyword_mode=Keyword.REQUIRED,
        keyword_after=True,
    ),
    # Wiek – tylko gdy w tekście jest imię i nazwisko. Same liczby lat („od 30 lat”,
    # „30 lat temu”, „10-letni kredyt”) zostają: maskujemy wyłącznie wiek osoby.
    Rule(
        "WIEK",
        _c(
            r"(?<!\w)(?i:mam|mamy|miałem|miałam|mialem|mialam|skończyłem|skończyłam|skonczylem|"
            r"skonczylam|kończę|koncze|skończę|skoncze)\s+"
            rf"{_AGE_ADVERB}(?P<v>{_AGE})"
        ),
        priority=13,
        requires_full_name=True,
    ),
    # Trzecia osoba tylko, gdy w tym samym zdaniu przed nią stoi osoba
    # („Ewa Kopacz ma 67 lat”, „sąsiadka ma 80 lat”), a nie rzecz („ustawa ma 30 lat”).
    Rule(
        "WIEK",
        _c(
            rf"(?:(?<=[\w,]\s)[{_UPPER}][{_LOWER}]+|(?<!\w)(?i:{_PERSON_NOUNS}|on|ona|jego|jej))"
            # Między osobą a wiekiem: bez końca zdania i bez innych liczb, ale nawias wolno
            # („Piotr Wiśniewski (ur. 1980) ma 44 lata”).
            r"(?!\w)(?:[^.!?\d\n()]|\([^)\n]{0,40}\)){0,30}?"
            r"(?<!\w)(?i:ma|miał|miała|mial|miala|mając\w*|majac\w*|skończył\w*|skonczyl\w*|"
            r"kończy|konczy|skończy|skonczy|liczy|liczył\w*|obchodzi\w*|świętuje|swietuje)\s+"
            rf"{_AGE_ADVERB}(?P<v>{_AGE})"
        ),
        priority=13,
        requires_full_name=True,
    ),
    Rule(
        "WIEK",
        _c(
            r"\(\s*(?P<v>(?i:lat|l\.|wiek)\s*:?\s*\d{1,3}|\d{1,3}\s*(?i:lat|lata|l\.|r\.\s?ż\.|rż))"
            r"\s*[),]"
        ),
        priority=13,
        requires_full_name=True,
    ),
    # „Jan Nowak (68)”, „Jan Nowak, 68 lat,”, „Jan Nowak, lat 68”
    Rule(
        "WIEK",
        _c(
            rf"(?<=[{_LOWER}])\s*(?:\(\s*(?P<v>\d{{1,3}})\s*\)"
            r"|,\s*(?P<w>(?i:lat\s+)?\d{1,3}(?:\s*(?i:lat|lata|l\.))?)(?=\s*[,.;)]|\s*$))"
        ),
        priority=13,
        requires_full_name=True,
    ),
    Rule(
        "WIEK",
        _c(
            r"(?<!\w)(?P<v>\d{1,3}\s*-?\s*(?i:latek|latka|latki|latkiem|latce|latkowi|latków|latkow|"
            r"latkami|latkę|latke))(?!\w)"
        ),
        priority=13,
        requires_full_name=True,
    ),
    Rule(
        "WIEK",
        _c(
            r"(?<!\w)(?P<v>\d{1,3}\s*-?\s*(?i:letni|letnia|letniego|letniej|letnim|letnią|letnie|"
            r"letnich))(?=\s+(?:"
            rf"[{_UPPER}][{_LOWER}]+|(?i:{_PERSON_NOUNS})))"
        ),
        priority=13,
        requires_full_name=True,
    ),
    Rule(
        "WIEK",
        _c(
            r"(?<!\w)(?i:w\s+wieku|wiek|wieku)\s*:?\s*(?:(?i:około|okolo|ok\.)\s*)?"
            r"(?P<v>\d{1,3}(?:\s*(?i:lat|lata))?)(?!\w)"
        ),
        priority=13,
        requires_full_name=True,
    ),
)
