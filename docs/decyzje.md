# Dziennik decyzji

Każda decyzja, która wpływa na drugą osobę lub na zgodność z zadaniem, trafia tutaj z datą i powodem.

## Podjęte

| Data | Decyzja | Powód |
| --- | --- | --- |
| 2026-11-21 | Źródła wyłącznie z białej listy, bez scrapingu stron | Konsultacja z mentorami: kontrola nad źródłami i licencjami, mniejsze ryzyko prawne |
| 2026-11-21 | LLM i embeddingi przez API zgodne z OpenAI, konfiguracja z `.env` | Możliwość zmiany dostawcy bez przebudowy (wymaganie z zadania) |
| 2026-11-21 | RAG z dynamicznie aktualizowanym indeksem w Qdrant | Wyszukiwanie hybrydowe (wektory + BM25), uruchamianie w Dockerze |

## Otwarte

| Temat | Opcje | Do kiedy |
| --- | --- | --- |
| Docelowy dostawca LLM i miejsce przetwarzania danych | FreeLLMAPI (development), dostawca z UE, model lokalny | przed SYNC 3 |
| Model embeddingów | do wyboru, musi dobrze obsługiwać polski | przed pierwszym indeksowaniem |
| Usuwanie danych nieużywanych przez 30 dni | tylko cache i treści ulotne (propozycja) albo cały korpus | przed SYNC 2 |
| Drugi kanał | Discord (adapter demo), SMS, WhatsApp | przed SYNC 3 |
| Framework RAG | LlamaIndex, LangChain, Haystack | przed SYNC 2 |

## Uwagi do otwartych decyzji

- **FreeLLMAPI** łączy darmowe konta różnych dostawców. Dokumentacja projektu zastrzega, że służy do osobistych eksperymentów, a współdzielenie kont w zespole może naruszać regulaminy dostawców. Miejsce przetwarzania danych zależy od dostawcy wybranego w łańcuchu fallback. Nadaje się do developmentu, ale przed demo trzeba wybrać i opisać docelowego dostawcę.
- **Usuwanie po 30 dniach:** dla źródeł pierwotnych (ustawy, oficjalne dane) brak użycia nie oznacza, że informacja jest nieaktualna. Propozycja: automatycznie usuwamy tylko cache i treści ulotne, a korpus kuratorowany aktualizujemy przez konektory.
