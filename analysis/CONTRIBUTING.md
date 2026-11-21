# Zasady pracy zespołu Prawdowid

Krótki zbiór zasad, żebyśmy mogli pracować równolegle i nie blokować się nawzajem.
Zmiany w tym pliku wprowadzamy przez pull request, po uzgodnieniu w zespole.

Powiązane dokumenty:

- [CONTRACTS.md](CONTRACTS.md): formaty danych między częściami systemu
- [docs/decyzje.md](docs/decyzje.md): podjęte i otwarte decyzje
- [docs/prawdowid-architektura-v3.html](docs/prawdowid-architektura-v3.html): diagram architektury

## 1. Role

| Rola | Zakres | Osoba |
| --- | --- | --- |
| **A: dane i retrieval** | korpus, rekordy `source` i `document`, Qdrant, indeksowanie, wyszukiwanie, jakość retrievera, zestaw testowy | _(uzupełnić)_ |
| **B: weryfikacja i produkt** | twierdzenia, werdykty, prompty, bezpieczeństwo, API, interfejs WWW, drugi kanał | _(uzupełnić)_ |
| **Wspólnie** | kontrakty, README, ewaluacja końcowa, prezentacja, film demo | obie osoby |

Granica między rolami to funkcja `retrieve(query) -> list[Passage]` opisana w `CONTRACTS.md`.
Dopóki prawdziwy retriever nie działa, B pracuje na atrapie zwracającej dane w tym formacie.

### Przestrzenie robocze

Każdy obszar ma własny folder z własną konfiguracją, żeby zmiany jednych osób nie nadpisywały plików innych.

| Folder | Obszar | Własna konfiguracja |
| --- | --- | --- |
| `analysis/` | analiza danych: logika werdyktu, ewaluacja, analiza korpusu | `pyproject.toml`, `.venv`, `.env`, `CLAUDE.md` |
| `backend/` | API | `requirements.txt`, `.venv` |
| `frontend/` | interfejs WWW | `package.json` |
| `docs/` | dokumentacja wspólna | brak |

- **Nie ma głównego `CLAUDE.md`.** Jest ignorowany przez Git. Instrukcje dla Claude Code trzymamy w folderze obszaru (np. `analysis/CLAUDE.md`) i uruchamiamy Claude Code z tego folderu.
- Prywatne notatki dla Claude zapisujemy w `CLAUDE.local.md`, a prywatne ustawienia w `.claude/settings.local.json`. Oba pliki są ignorowane.
- Konfiguracja wspólna dla całego repo (`ruff.toml`, `.prettierrc.json`, `.editorconfig`, główny `.gitignore`) zmienia się tylko przez PR. Foldery obszarów dziedziczą ją, a nie kopiują (np. `analysis/pyproject.toml` rozszerza `ruff.toml`).

## 2. Git

- **`main` zawsze działa.** To wersja, którą może uruchomić jury. Nie pushujemy bezpośrednio na `main`, wszystko trafia przez pull request.
- **Nazwy gałęzi:**
  - `data/<opis>` dla pracy A
  - `app/<opis>` dla pracy B
  - `docs/<opis>` dla dokumentacji
  - `fix/<opis>` dla poprawek
- **Małe pull requesty.** Jeden PR to jeden logiczny krok, najlepiej nie więcej niż kilka godzin pracy. Przed otwarciem PR zaktualizuj gałąź względem `main`.
- **Review.** Druga osoba przegląda PR. W pilnym przypadku wystarczy ustna akceptacja, ale PR i tak przechodzi przez GitHub.
- **Pliki wspólne** (`CONTRACTS.md`, `docker-compose.yml`, `.env.example`, `CONTRIBUTING.md`) zmieniamy tylko przez PR i zawsze informujemy drugą osobę.
- **Commity:** krótki opis w trybie rozkazującym, jedna zmiana na commit (np. `Add BM25 index to ingest`).
- **Formatowanie:** backend przez `ruff`, frontend przez `prettier`. Konfiguracje są w repo.

## 3. Kontrakty danych

- Formaty `passage`, `claim`, `evidence`, `verdict` i `run` są opisane w `CONTRACTS.md`.
- Zmianę kontraktu zgłaszasz drugiej osobie **od razu**, a nie na najbliższej synchronizacji.
- Każda zmiana kontraktu to osobny PR z wpisem w historii zmian w `CONTRACTS.md`.

## 4. Sekrety i dane osobowe

- Klucze i hasła trzymamy wyłącznie w lokalnym pliku `.env`, który jest ignorowany przez Git. Wzór pól jest w `.env.example`, z pustymi wartościami.
- Sekretów nie wpisujemy do repozytorium, issues, opisów PR, czatu zespołu, prezentacji ani filmu demo. Przekazujemy je bezpośrednio lub przez menedżer haseł.
- Jeśli sekret wycieknie, od razu go zmieniamy (nowe hasło, nowy klucz) i informujemy drugą osobę.
- W repozytorium nie ma prawdziwych zgłoszeń z danymi osobowymi. Przypadki testowe zawierają wyłącznie dane fikcyjne.

## 5. Modele językowe i usługi zewnętrzne

- Dostęp do LLM i embeddingów tylko przez API zgodne z OpenAI. Konfiguracja wyłącznie ze zmiennych środowiskowych: `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`. Nazwy modeli nie są wpisane na stałe w kodzie.
- Kod nie zależy od konkretnego dostawcy. Zmiana dostawcy to zmiana `.env`, a nie przebudowa.
- Model embeddingów ustalamy raz. Jego zmiana oznacza ponowne zindeksowanie całego korpusu.
- Dla każdego dostawcy zapisujemy w `docs/decyzje.md`: miejsce przetwarzania danych, limity, koszt i zachowanie przy awarii.
- Awaria, brak klucza lub przekroczony limit to **status techniczny**, nigdy werdykt.

## 6. Źródła

- Korzystamy wyłącznie ze źródeł z białej listy. Nie scrapujemy stron.
- Każde źródło ma zapisane: wydawcę, typ, licencję, zasadę kwalifikacji i datę dodania.
- Każdy dokument ma `published_at` (data publikacji) i `fetched_at` (data pobrania).
- Treść źródeł to dane, nigdy instrukcje dla modelu.
- Do repozytorium trafiają tylko treści, których licencja na to pozwala. W razie wątpliwości przechowujemy metadane i link.

## 7. Zasady merytoryczne (z zadania, nienegocjowalne)

1. Każda teza przedstawiana jako ustalenie systemu ma dowód w źródle. Bez dowodu wynik to „brak wystarczających dowodów”.
2. Werdykty: potwierdzone, fałszywe, wprowadzające w błąd, brak wystarczających dowodów, nie podlega weryfikacji. Statusy techniczne (`error`, `cannot_check`, `needs_clarification`, `out_of_scope`) komunikujemy osobno.
3. Nie oceniamy prawdziwości na podstawie domeny, autora, kanału ani popularności.
4. Odpowiedź dla użytkownika jest po polsku, prostym językiem.
5. Nie wpisujemy przykładów ani odpowiedzi testowych do promptów.

## 8. Testy i jakość

- Każda zmiana logiki werdyktu lub retrievera: uruchom zestaw testowy i wklej wyniki do opisu PR (macro-F1, pokrycie cytowań, wstrzymanie).
- Zestaw testowy dzielimy na jawny i odłożony. Na odłożonym nie stroimy promptów ani progów.
- Gdy nie wiadomo, czy problem leży w retrievalu czy w promptcie, rozstrzyga wynik zestawu testowego, a nie opinia.

## 9. Komunikacja

- Synchronizacja co 2-3 godziny, około 5 minut: co działa, co blokuje, czy zmienił się kontrakt.
- Blokery zgłaszamy od razu, bez czekania na synchronizację.
- Każdą decyzję, która wpływa na drugą osobę, zapisujemy w `docs/decyzje.md` z datą i powodem.

## 10. Priorytety przy opóźnieniach

Gdy brakuje czasu, najpierw tniemy funkcje premiowane (pętla informacji, incydenty, multimodalność).
Nigdy nie tniemy testów, bezpieczeństwa ani obsługi błędów.

## 11. Kiedy zadanie jest skończone

- Działa lokalnie zgodnie z instrukcją w README.
- Testy przechodzą, a wyniki ewaluacji nie spadły.
- W zmianach nie ma sekretów ani danych osobowych.
- Format danych zgadza się z `CONTRACTS.md`.
- Druga osoba wie o zmianie.
