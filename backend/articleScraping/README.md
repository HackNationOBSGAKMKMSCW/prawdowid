# articleScraping: pobieranie pełnych artykułów

`articleScraping.run` pobiera pełne treści artykułów znalezionych dla tezy i zwraca końcowy, ustrukturyzowany wynik (`ScrapingReport`).

```python
submitted_at = datetime.now(UTC)                      # albo czas z zapytania użytkownika
analysis = await textAnalysis.run(text, started_at=submitted_at)
results, trusted = await asyncio.gather(apiReading.run(analysis), trustedSources.run(analysis))
report = await articleScraping.run(analysis, results, trusted=trusted)
# lub jawnie: articleScraping.run(..., submitted_at=submitted_at)
```

## Wynik

```jsonc
{
  "submitted_at": "2026-11-22T08:30:00Z",   // kiedy użytkownik wysłał zapytanie
  "user_input": "  Ziemia jest płaska!!  ", // input użytkownika bez żadnych zmian
  "articles": [                             // pobrane artykuły
    {
      "url": "https://demagog.org.pl/fake_news/…",
      "site": "demagog.org.pl",             // strona, patrz niżej
      "title": "Ziemia jest płaska, bo tak mówi Biblia? …",
      "published_at": "2026-02-15T00:00:00Z",
      "text": "… cała treść …",              // pełny tekst, do 50 000 znaków
      "author": "Jan Kowalski",             // autor podpisany na stronie, jeśli jest
      "publisher": "Demagog",               // instytucja lub redakcja źródła
      "truncated": false,                   // true, gdy tekst przekroczył limit
      "source": "fact_check"                // fact_check | trusted_source | user_text
    }
  ],
  "sources": [                              // WSZYSTKIE linki znalezione dla tezy
    {"url": "…", "site": "gov.pl/web/rcb", "kind": "trusted_source", "title": "…",
     "publisher": "RCB", "status": "scraped"}
    // status: scraped | failed | not_scraped (zapas, niepotrzebny) | reference (dashboard, np. IMGW)
  ],
  "distinct_sites": 2,                      // z ilu różnych stron są artykuły
  "min_sites_met": true,                    // czy osiągnięto minimum 2 stron
  "failures": [{"url": "…", "kind": "Timeout", "status_code": null, "source": "trusted_source"}],
  "finished_at": "2026-11-22T08:30:04Z"
}
```

`author` jest tylko wtedy, gdy strona podpisuje autora. Komunikaty urzędów zwykle nie mają podpisu, a wtedy twórcę opisuje `publisher`. Stare nazwy pól `started_at` i `user_text` działają w Pythonie jako aliasy.

## Co najmniej dwie różne strony

„Strona” to host bez `www.` (`demagog.org.pl`, `moje.cert.pl`). Na portalu gov.pl każdy serwis instytucji liczy się osobno (`gov.pl/web/rcb`, `gov.pl/web/gis`).

1. Przy wyborze linków (limit `ARTICLE_MAX_LINKS`, domyślnie 5) najlepszy link z drugiej strony zawsze trafia do puli. Jedna strona nie może zająć całego limitu.
2. Gdy po pobraniu artykuły pochodzą z mniej niż 2 stron (bo strona nie odpowiedziała albo to nie był artykuł), pobierane są linki zapasowe z innych stron, w ramach `ARTICLE_BATCH_TIMEOUT`.
3. Jeśli żadna inna strona z białej listy nie ma pasującego materiału, wynik ma `min_sites_met: false`. Moduł nie pobiera stron niezwiązanych z tezą tylko po to, żeby zaliczyć minimum. Rozwiązaniem jest wtedy dopisanie źródeł do `trustedSources/whitelist.py`.
