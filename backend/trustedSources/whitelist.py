"""Hardcoded whitelist of trusted sources (temporary until the PostgreSQL table).

Only these sites are searched. gov.pl entries are scoped to their own subsite
(``/web/<id>``); there is no portal-wide gov.pl search. Demagog is searched
through the Google Fact Check API (``reviewPublisherSiteFilter``).

``adapter`` set here is fixed (``adapter_locked``); without it the type is
detected automatically on first use.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WhitelistEntry:
    """One row of the future ``trusted_sources`` table."""

    url: str
    name: str
    topics: tuple[str, ...] = ()
    description: str = ""
    adapter: str | None = None
    enabled: bool = True
    params: dict[str, object] = field(default_factory=dict)


WHITELIST: tuple[WhitelistEntry, ...] = (
    WhitelistEntry(
        "https://demagog.org.pl/",
        "Demagog",
        topics=("fact-checking", "dezinformacja", "fake news"),
    ),
    WhitelistEntry(
        "https://odyseusz.gov.pl/",
        "Odyseusz (MSZ) – rejestracja podróży",
        topics=("podróże zagraniczne", "ostrzeżenia dla podróżnych", "konsulat"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/gov/ostrzezenia",
        "gov.pl – ostrzeżenia",
        topics=("ostrzeżenia", "alerty"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/mswia/regionalny-system-ostrzegania",
        "MSWiA – Regionalny System Ostrzegania",
        topics=("ostrzeżenia", "RSO"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/rcb/raport-dobowy3",
        "RCB – raport dobowy",
        topics=("zarządzanie kryzysowe", "alert RCB"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/rcb/strona-glowna-rzadowego-centrum-bezpieczenstwa",
        "Rządowe Centrum Bezpieczeństwa",
        topics=("zarządzanie kryzysowe", "alert RCB", "dezinformacja"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/kgpsp/aktualnosci",
        "Państwowa Straż Pożarna – aktualności",
        topics=("pożar", "straż pożarna", "akcja ratownicza"),
    ),
    WhitelistEntry(
        "https://policja.pl/pol/aktualnosci",
        "Policja – aktualności",
        topics=("policja", "przestępstwo", "bezpieczeństwo"),
    ),
    WhitelistEntry(
        "https://mazowiecka.policja.gov.pl/ra/aktualnosci/aktualnosci",
        "Policja mazowiecka – aktualności",
        topics=("policja", "Mazowsze"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/obrona-narodowa/aktualnosci5",
        "Ministerstwo Obrony Narodowej – aktualności",
        topics=("wojsko", "obronność", "armia"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/gis/ostrzezenia",
        "Główny Inspektorat Sanitarny – ostrzeżenia",
        topics=("zdrowie", "żywność", "szczepienia", "epidemia"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/paa/panstwowa-agencja-atomistyki",
        "Państwowa Agencja Atomistyki",
        topics=("promieniowanie", "atom", "elektrownia jądrowa"),
    ),
    WhitelistEntry(
        "https://monitoring.paa.gov.pl/",
        "PAA – monitoring promieniowania",
        topics=("promieniowanie", "skażenie radiacyjne", "radiacja", "awaria jądrowa"),
        description="Bieżące pomiary mocy dawki promieniowania gamma w Polsce.",
        adapter="reference",
    ),
    WhitelistEntry(
        "https://powietrze.gios.gov.pl/pjp/",
        "GIOŚ – jakość powietrza",
        topics=("jakość powietrza", "smog", "zanieczyszczenie powietrza", "pyły PM10"),
        description="Bieżące pomiary jakości powietrza ze stacji monitoringu.",
        adapter="reference",
    ),
    WhitelistEntry(
        "https://moje.cert.pl/komunikaty/",
        "CERT Polska – komunikaty",
        topics=("cyberbezpieczeństwo", "phishing", "oszustwo internetowe", "atak hakerski"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/infrastruktura",
        "Ministerstwo Infrastruktury",
        topics=("transport", "infrastruktura"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/infrastruktura/aktualnosci",
        "Ministerstwo Infrastruktury – aktualności",
        topics=("transport", "kolej", "drogi"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/infrastruktura/prawa-pasazerow",
        "Ministerstwo Infrastruktury – prawa pasażerów",
        topics=("prawa pasażera", "odszkodowanie"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/infrastruktura/infolinia-dla-obywatela",
        "Ministerstwo Infrastruktury – infolinia",
        topics=("infolinia",),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/infrastruktura/dane-kontaktowe",
        "Ministerstwo Infrastruktury – kontakt",
        topics=("kontakt",),
    ),
    WhitelistEntry(
        "https://drogi.gddkia.gov.pl/informacje-drogowe",
        "GDDKiA – informacje drogowe",
        topics=("utrudnienia drogowe", "drogi krajowe", "autostrada", "objazd"),
    ),
    WhitelistEntry(
        "https://drogi.gddkia.gov.pl/mapy/mapa-informacji-drogowej",
        "GDDKiA – mapa informacji drogowej",
        topics=("utrudnienia drogowe", "zamknięta droga", "korek", "wypadek drogowy"),
        description="Interaktywna mapa utrudnień na drogach krajowych.",
        adapter="reference",
    ),
    WhitelistEntry(
        "https://drogi.gddkia.gov.pl/informacje-drogowe/lista-utrudnien",
        "GDDKiA – lista utrudnień",
        topics=("utrudnienia drogowe", "zamknięta droga", "remont drogi"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/gddkia/informacja-drogowa---19-111",
        "GDDKiA – informacja drogowa 19 111",
        topics=("drogi krajowe", "utrudnienia drogowe"),
    ),
    WhitelistEntry(
        "https://ulc.gov.pl/",
        "Urząd Lotnictwa Cywilnego",
        topics=("lotnictwo", "lotnisko", "loty", "drony"),
    ),
    WhitelistEntry(
        "https://ulc.gov.pl/prawa-pasazera",
        "ULC – prawa pasażera",
        topics=("prawa pasażera", "odwołany lot", "opóźniony lot", "odszkodowanie"),
    ),
    WhitelistEntry(
        "https://ulc.gov.pl/prawa-pasazera/poradnik-dla-pasazerow",
        "ULC – poradnik dla pasażerów",
        topics=("prawa pasażera", "bagaż", "odwołany lot"),
    ),
    WhitelistEntry(
        "https://portalpasazera.pl/",
        "Portal Pasażera (PKP PLK)",
        topics=("rozkład jazdy", "pociąg", "utrudnienia na kolei", "opóźnienie pociągu"),
        description="Rozkład jazdy i bieżące utrudnienia na kolei.",
        adapter="reference",
    ),
    WhitelistEntry(
        "https://utk.gov.pl/pl/pasazerowie",
        "Urząd Transportu Kolejowego – pasażerowie",
        topics=("kolej", "pociąg", "prawa pasażera"),
    ),
    WhitelistEntry(
        "https://kgsok.pl/",
        "Krajowy System Ostrzegania o Katastrofach",
        topics=("ostrzeżenia", "katastrofa"),
    ),
    WhitelistEntry(
        "https://www.sar.gov.pl/",
        "Morska Służba Poszukiwania i Ratownictwa (SAR)",
        topics=("ratownictwo morskie", "Bałtyk", "akcja ratunkowa"),
    ),
    WhitelistEntry(
        "https://www.umgdy.gov.pl/",
        "Urząd Morski w Gdyni",
        topics=("żegluga", "port", "Bałtyk"),
    ),
    WhitelistEntry(
        "https://www.ums.gov.pl/bezpieczenstwo-morskie/warunki-zeglugi",
        "Urząd Morski w Szczecinie – warunki żeglugi",
        topics=("żegluga", "warunki żeglugi", "zalew"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/wody-polskie/komunikaty-nawigacyjne",
        "Wody Polskie – komunikaty nawigacyjne",
        topics=("żegluga śródlądowa", "rzeka", "powódź", "susza"),
    ),
    WhitelistEntry(
        "https://meteo.imgw.pl/",
        "IMGW – meteo (ostrzeżenia pogodowe)",
        topics=("pogoda", "ostrzeżenie meteorologiczne", "burza", "upał", "mróz", "wichura", "silny wiatr", "opady"),
        description="Prognozy i ostrzeżenia meteorologiczne IMGW-PIB.",
        adapter="reference",
    ),
    WhitelistEntry(
        "https://hydro.imgw.pl/",
        "IMGW – hydro (stany rzek)",
        topics=("powódź", "stan rzek", "ostrzeżenie hydrologiczne", "susza", "wezbranie"),
        description="Bieżące stany wód i ostrzeżenia hydrologiczne IMGW-PIB.",
        adapter="reference",
    ),
    WhitelistEntry(
        "https://baltyk.imgw.pl/",
        "IMGW – Bałtyk",
        topics=("Bałtyk", "sztorm", "stan morza"),
        description="Warunki i prognozy dla Bałtyku.",
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/mswia",
        "Ministerstwo Spraw Wewnętrznych i Administracji",
        topics=("bezpieczeństwo wewnętrzne", "administracja"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/dyplomacja/informacje-dla-podrozujacych",
        "MSZ – informacje dla podróżujących",
        topics=("podróże zagraniczne", "ostrzeżenia dla podróżnych"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/premier",
        "Kancelaria Prezesa Rady Ministrów",
        topics=("rząd", "premier"),
    ),
    # Gospodarka, praca, świadczenia, zdrowie, edukacja, prawo.
    WhitelistEntry(
        "https://www.gov.pl/web/rodzina",
        "Ministerstwo Rodziny, Pracy i Polityki Społecznej",
        topics=("świadczenia", "800 plus", "płaca minimalna", "emerytury", "rynek pracy"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/finanse",
        "Ministerstwo Finansów",
        topics=("podatki", "budżet", "inflacja", "finanse publiczne"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/dialog",
        "Rada Dialogu Społecznego",
        topics=("płaca minimalna", "wynagrodzenia", "dialog społeczny"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/rozwoj-technologia",
        "Ministerstwo Rozwoju i Technologii",
        topics=("gospodarka", "przedsiębiorczość", "mieszkalnictwo"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/zdrowie",
        "Ministerstwo Zdrowia",
        topics=("zdrowie", "szczepienia", "NFZ", "leki"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/edukacja",
        "Ministerstwo Edukacji Narodowej",
        topics=("szkoły", "edukacja"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/sprawiedliwosc",
        "Ministerstwo Sprawiedliwości",
        topics=("prawo", "sądy"),
    ),
    WhitelistEntry(
        "https://www.gov.pl/web/klimat",
        "Ministerstwo Klimatu i Środowiska",
        topics=("energia", "klimat", "środowisko"),
    ),
    # stat.gov.pl przekierowuje na nowy serwis GUS (kanał RSS z komunikatami).
    WhitelistEntry(
        "https://new.stat.gov.pl/",
        "Główny Urząd Statystyczny",
        topics=("statystyka", "inflacja", "wynagrodzenia", "bezrobocie", "PKB", "ludność"),
    ),
    # Akty prawne po tytule: API ELI Sejmu (adapter sejm_eli, linki do tekstu aktu i ISAP).
    WhitelistEntry(
        "https://isap.sejm.gov.pl/",
        "Sejm – akty prawne (ELI / ISAP)",
        topics=("prawo", "ustawa", "rozporządzenie", "Dziennik Ustaw", "Monitor Polski"),
    ),
    # Kontekst encyklopedyczny dla faktów ogólnych (geografia, historia, instytucje).
    # Zaufanie "other": to nie jest źródło urzędowe.
    WhitelistEntry(
        "https://pl.wikipedia.org/",
        "Wikipedia (polska)",
        topics=("encyklopedia", "geografia", "historia", "instytucje"),
        description="Kontekst encyklopedyczny; nie jest źródłem urzędowym.",
    ),
    WhitelistEntry(
        "https://www.nato.int/",
        "NATO – aktualności",
        topics=("NATO", "sojusz", "obronność", "Ukraina"),
    ),
    WhitelistEntry(
        "https://poland.representation.ec.europa.eu/index_pl",
        "Komisja Europejska – Przedstawicielstwo w Polsce",
        topics=("Unia Europejska", "Komisja Europejska", "fundusze UE", "prawo UE"),
    ),
    WhitelistEntry(
        "https://www.zus.pl/",
        "Zakład Ubezpieczeń Społecznych",
        topics=("emerytury", "składki", "świadczenia"),
    ),
    # Fact-checkery szukane przez Google Fact Check API (reviewPublisherSiteFilter).
    WhitelistEntry(
        "https://konkret24.tvn24.pl/",
        "Konkret24",
        topics=("fact-checking", "dezinformacja"),
    ),
    WhitelistEntry(
        "https://sprawdzam.afp.com/",
        "AFP Sprawdzam",
        topics=("fact-checking", "dezinformacja"),
    ),
    WhitelistEntry(
        "https://fakenews.pl/",
        "FakeNews.pl",
        topics=("fact-checking", "dezinformacja"),
    ),
)
