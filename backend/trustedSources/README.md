# trustedSources: biała lista źródeł prawdy

Moduł szuka pasujących do sprawdzanej tezy materiałów **wyłącznie na stronach z białej listy**: komunikatów urzędów, ostrzeżeń i fact-checków. Na liście są konkretne serwisy gov.pl, strony urzędów oraz Demagog. Demagoga odpytujemy przez Google Fact Check API. Nie ma wyszukiwania po całym portalu gov.pl.

```python
analysis = await textAnalysis.run(text)                 # statements + search_queries
results, trusted = await asyncio.gather(apiReading.run(analysis), trustedSources.run(analysis))
report = await articleScraping.run(analysis, results, trusted=trusted)   # pobiera też pełne teksty
```

`trustedSources.run` nigdy nie rzuca wyjątku. Błędy pojedynczych źródeł trafiają do `report.failures`, a reszta źródeł działa dalej.

## Lista stron

Na razie lista jest zahardkodowana w [whitelist.py](whitelist.py), jako krotka `WHITELIST` z wpisami `WhitelistEntry(url, name, topics, description, adapter, enabled)`. Później przeniesiemy ją do tabeli PostgreSQL. Rejestr czyta listę przez interfejs `SourceStore.load()` ([store.py](store.py)), więc wystarczy napisać `PostgresSourceStore` i przekazać go do `SourceRegistry(store=...)`. Rejestr przeładowuje listę co 5 minut (`refresh_seconds`). Proponowany schemat tabeli:

```sql
CREATE TABLE trusted_sources (
    url         text PRIMARY KEY,
    name        text NOT NULL,
    topics      text[] NOT NULL DEFAULT '{}',
    description text NOT NULL DEFAULT '',
    adapter     text,              -- NULL = rozpoznaj automatycznie
    params      jsonb NOT NULL DEFAULT '{}',
    enabled     boolean NOT NULL DEFAULT true
);
```

Typ strony, wykryty w czasie działania, jest trzymany w pamięci procesu i przetrwa przeładowanie listy. Po restarcie wykrywanie uruchamia się ponownie: przy `warm` przy starcie serwera albo w tle przy pierwszym wyszukiwaniu.

**Podgląd** (router w `trustedSources.api`, tylko odczyt):

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/api/trusted-sources` | lista źródeł (`?enabled_only=true`) |
| GET | `/api/trusted-sources/{id}` | jedno źródło |
| POST | `/api/trusted-sources/{id}/check` | ponowne rozpoznanie typu |
| POST | `/api/trusted-sources/search` | `{text?, queries?}` → podgląd wyników |

**CLI** (z katalogu `backend/`):

```bash
python -m trustedSources list
python -m trustedSources check --all          # rozpoznaj typ wszystkich stron
python -m trustedSources search "alert RCB silny wiatr"   # frazy z textAnalysis jak w pipeline; --raw = dokładnie ten tekst
python -m trustedSources warm                 # pobierz z góry listingi i feedy do cache
```

## Typy stron (adaptery)

| Adapter | Kiedy | Jak szuka |
|---|---|---|
| `govpl_search` | `www.gov.pl/web/<serwis>/…` (bez sieci) | Publiczne API wyszukiwarki portalu `/api/data/search`, zawsze zawężone do serwisu z listy (`ministryId`). Wyniki spoza `/web/<serwis>/` są odrzucane. Sam adres `https://www.gov.pl/` jest ignorowany. |
| `fact_check_publisher` | domena redakcji fact-checkingowej (Demagog, Konkret24, AFP, fakenews.pl) | Google Fact Check z `reviewPublisherSiteFilter`, wymaga `GOOGLE_FACT_CHECK_API_KEY`. |
| `feed` | strona ma RSS/Atom (`<link rel=alternate>` albo `/feed/`, `/rss.xml`) | Ostatnie wpisy z feedu, z cache. |
| `listing` | strona to lista artykułów (co najmniej 5 linków z tytułami pod tą samą ścieżką) | Linki i tytuły ze strony (z pominięciem nawigacji), z cache. |
| `sitemap` | `robots.txt`, `/sitemap.xml`, `/wp-sitemap.xml` | Tylko najnowsze pod-sitemapy (maks. 3, z ostatnich 90 dni), nigdy całe archiwum. |
| `reference` | aplikacja JS, mapa, pomiary (nic do przeszukania) | Zwraca sam link „sprawdź na bieżąco”, gdy teza pasuje do nazwy, opisu lub `topics` źródła. |

Dlatego przy dashboardach (IMGW, GIOŚ, monitoring PAA) warto podać `topics`. Typ ustawiony ręcznie przez `adapter` we wpisie ma `adapter_locked` i automatyczne rozpoznawanie go nie nadpisuje.

Kolejność rozpoznawania: gov.pl → redakcja fact-checkingowa → feed → listing → sitemap → reference. Jeśli strona nie odpowiada, wpis zostaje jako `pending` z błędem w `last_check`. Próba jest ponawiana najwcześniej po godzinie albo od razu przy `check`.

## Dopasowanie do tezy

Zapytaniami są frazy `search_queries` z textAnalysis, potem tezy (`statements`), a na końcu słowa kluczowe. Każde trafienie jest oceniane lokalnie ([ranking.py](ranking.py)):

- Tekst jest normalizowany: małe litery, bez polskich znaków, z prostym stemmerem: obcięcie końcówki i prefiks 7 liter.
- Trafienie musi zawierać wszystkie słowa zapytania 1–2-wyrazowego, 2 z 3 albo połowę słów dłuższego zapytania. Trafienia o tym samym tytule są scalane. Dzięki temu „płaska Ziemia” nie trafia w „Wodociąg Płaska”.
- Kolejność ustala BM25, z bonusem za fact-checkera i świeżość.
- URL musi należeć do domeny źródła.
- Limity: 3 trafienia na źródło i 10 łącznie.

## Bezpieczeństwo

- Każdy dowolny URL (probe, listing, feed, sitemap) jest pobierany przez `articleScraping.safe_http.SafeFetcher`, który:
  - waliduje każde przekierowanie;
  - odrzuca adresy prywatne i localhost;
  - przypina połączenie do sprawdzonego IP (ochrona przed DNS rebinding);
  - pilnuje limitu rozmiaru.
- XML jest parsowany bez encji i bez sieci (ochrona przed XXE). Gzip ma limit 10 MB po rozpakowaniu.

## Konfiguracja (env)

| Zmienna | Domyślnie | Opis |
|---|---|---|
| `TRUSTED_SOURCE_TIMEOUT` | `6` | timeout na źródło (s) |
| `TRUSTED_SOURCE_CACHE_TTL` | `1200` | ważność cache listingów, feedów i sitemap (s); przy błędzie podawana jest ostatnia znana wersja |
| `TRUSTED_SOURCES_WARM` | `true` | rozgrzewanie cache przy starcie serwera (tryb live) |

## Nowy typ strony

```python
# trustedSources/adapters/moj_typ.py
from . import SearchContext, SourceAdapter, register_adapter

@register_adapter("moj_typ")
class MojTypAdapter(SourceAdapter):
    async def search(self, sources, queries, ctx: SearchContext):
        ...  # zwróć list[EvidenceHit]; ranking i limity zrobi service
```

Moduł trzeba dopisać do importu na końcu [adapters/\_\_init\_\_.py](adapters/__init__.py), a w `detect.py` dodać regułę rozpoznawania (opcjonalnie). Do stron spoza stałych API używaj `ctx.fetcher` (SafeFetcher), do znanych hostów API `ctx.http`.
