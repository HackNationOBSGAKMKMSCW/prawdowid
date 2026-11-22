# knownDisinfo: twierdzenia z bazy EUvsDisinfo

Jeśli twierdzenie z inputu jest w bazie [EUvsDisinfo](https://euvsdisinfo.eu), czyli w rejestrze prokremlowskiej dezinformacji z ponad 19 tys. przypadków, oznaczamy je jednoznacznie jako **zweryfikowaną rosyjską dezinformację**. Robi to [verification/disinfo.py](../verification/disinfo.py), które nadpisuje werdykt tez.

Teraz baza jest odpytywana przez serwer **MCP EUvsDisinfo**. Docelowo przeniesiemy ją do PostgreSQL ([niżej](#przejście-na-postgresql)).

## Jak działa

```
twierdzenia (textAnalysis)
  └─ LLM: 1–3 krótkie angielskie zapytania na twierdzenie   (baza jest po angielsku)
  └─ MCP search(query)  → tylko wpisy claim_review, deduplikacja po linku, maks. 5 kandydatów
  └─ LLM-sędzia: „czy któryś przypadek to TA SAMA teza?”     → case_id albo null
```

- **Zasada ostrożności.** Trafienie oznacza twierdzenie jako dezinformację, więc nie może być zgadywaniem. Te przypadki dają **brak trafienia**, a w `warnings` pojawia się ostrzeżenie:
  - ten sam temat bez tej samej tezy;
  - identyfikator spoza pokazanych kandydatów;
  - niepoprawny JSON;
  - błąd modelu.
- **Jeśli LLM nie przygotuje zapytań**, w ich miejsce idzie sama treść twierdzenia.
- **Wpisy `article`** to analizy EUvsDisinfo, a nie tezy, więc są pomijane.
- **`run()` nigdy nie zgłasza wyjątku.** Zwraca `DisinfoCheck` z jednym z trzech statusów:
  - `ok`: sprawdzenie się udało;
  - `disabled`: brak klucza;
  - `error`: baza jest nieosiągalna (szczegóły w `warnings`).

```python
check = await knownDisinfo.run(analysis)      # analysis.statements z textAnalysis
for hit in check.matches:                     # StatementCheck z ustawionym .match
    hit.index, hit.statement, hit.match.url, hit.reason
```

## MCP EUvsDisinfo

- **Adres:** `https://mcp.euvsd.info/mcp`, transport Streamable HTTP (JSON-RPC 2.0).
- **Tryb bezstanowy:** każde wywołanie to jedno żądanie z własnym `mcp-session-id`, bez `initialize`.
- **Klucz** idzie w nagłówku `X-API-Key`, nigdy w URL-u ani w logach.
- **Odpowiedź `search`:** `structuredContent.results[]`, każdy wpis to `{type: "claim_review" | "article", title, content (HTML), link}`.
- **Pozostałe narzędzia serwera** (`cases`, `articles`, `narratives`) nie są używane.

## CLI

```powershell
.venv\Scripts\python -m knownDisinfo --health                 # stan serwera (bez klucza)
.venv\Scripts\python -m knownDisinfo --tools                  # narzędzia MCP
.venv\Scripts\python -m knownDisinfo --search "NATO attack"   # surowe wyszukiwanie, bez LLM
.venv\Scripts\python -m knownDisinfo "NATO przygotowuje atak na Rosję"   # pełne sprawdzenie
```

## Konfiguracja (główny `.env` projektu)

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `EUvsDisinfo_API_KEY` | brak | Klucz MCP. Bez niego sprawdzenie ma status `disabled`. |
| `EUVSDISINFO_MCP_URL` | `https://mcp.euvsd.info/mcp` | Adres serwera MCP. |
| `EUVSDISINFO_MCP_TIMEOUT` | `20` | Limit czasu jednego wywołania w sekundach. |
| `KNOWN_DISINFO_MAX_CANDIDATES` | `5` | Maksymalna liczba kandydatów pokazywanych sędziemu na jedno twierdzenie. |
| `KNOWN_DISINFO_ENABLED` | `true` | `false` wyłącza sprawdzenie. |
| `KNOWN_DISINFO_REASONING_EFFORT` | `none` | Wartość `reasoning_effort` w wywołaniach LLM. `none` wyłącza myślenie Qwen3, co skraca odpowiedź z około 15 s do około 1 s. Pusta wartość nie wysyła parametru. Jeśli endpoint odrzuci ten parametr, kolejne wywołania idą bez niego. |

Model to ten sam, którego używa textAnalysis (`FREELLM_*`).

## Przejście na PostgreSQL

Dopasowanie korzysta wyłącznie z interfejsu `DisinfoStore` ([store.py](store.py)):

```python
class PostgresDisinfoStore:
    async def search(self, query: str, limit: int) -> list[DisinfoCase]: ...

check = await knownDisinfo.run(analysis, store=PostgresDisinfoStore(...))
```

Wyszukiwanie w tabeli może być pełnotekstowe albo wektorowe, na przykład na embeddingach `bge-m3` z serwera Ollama. Sędzia LLM i nadpisywanie werdyktu zostają bez zmian.
