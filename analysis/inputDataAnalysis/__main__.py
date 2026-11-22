"""Demo: ``python -m inputDataAnalysis [nazwa_przykładu ...]`` (z katalogu analysis/).

Wymaga uzupełnionego głównego pliku ``.env``. Bez argumentów uruchamia wszystkie przykłady.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import date
from typing import Any

from .llm import reset_clients
from .pipeline import analyze_async

EXAMPLES: dict[str, dict[str, Any]] = {
    "A_emocje": {
        "text": "Ta skandaliczna zdrada bezwzględnych zdrajców z ministerstwa to zbrodniczy plan "
        "przeciwko zwykłym ludziom.",
        "sources": [],
    },
    "B_straszenie": {
        "text": "Jeśli tego nie zatrzymamy, wszyscy poniesiemy konsekwencje. To dopiero początek "
        "nadchodzącej katastrofy dla polskich rodzin.",
        "sources": [],
    },
    "C_spisek": {
        "text": "Awaria sieci i podwyżki cen prądu w tym samym tygodniu? To nie może być przypadek. "
        "Wszystko zostało wcześniej zaplanowane, a media milczą, bo ktoś im zabronił.",
        "sources": [],
    },
    "D_pilnosc": {
        "text": "Natychmiast udostępnij, zanim to usuną! Musisz dowiedzieć się o tym teraz, to ostatnia "
        "szansa, żeby poznać prawdę o szczepionkach.",
        "sources": [],
    },
    "E_brak_zrodla": {
        "text": "Eksperci twierdzą, że woda z kranu w dużych miastach jest coraz bardziej "
        "niebezpieczna. Badania pokazują wzrost zachorowań o 40%.",
        "sources": [],
    },
    "F_wyolbrzymienie": {
        "text": "Po jednym incydencie w Gdańsku widać, że nikt w Polsce nie jest już bezpieczny na "
        "ulicach. To bezprecedensowa, masowa fala przemocy.",
        "sources": [],
    },
    "G_cherry_picking": {
        "text": "Przestępczość w Polsce rośnie: w lutym 2024 r. odnotowano o 15% więcej kradzieży "
        "niż w styczniu 2024 r.",
        "article_date": date(2024, 4, 2),
        "sources": [
            {
                "id": "kgp-2024",
                "title": "Statystyki KGP 2023",
                "published_at": "2024-03-28",
                "content": "W 2023 r. liczba kradzieży spadła o 8% w porównaniu z 2022 r. i była "
                "najniższa od 20 lat. Luty jest co roku miesiącem z wyraźnie wyższą liczbą "
                "kradzieży niż styczeń, co wynika z sezonowości. W lutym 2024 r. liczba kradzieży "
                "była o 15% wyższa niż w styczniu 2024 r., ale o 6% niższa niż w lutym 2023 r.",
            }
        ],
    },
    "neutralny": {
        "text": "Rada Miasta Wrocławia przyjęła 14 marca 2024 r. budżet na rok 2024. Za uchwałą "
        "głosowało 25 radnych, przeciw było 10.",
        "article_date": date(2024, 3, 15),
        "sources": [
            {
                "id": "bip-wroclaw",
                "title": "BIP Wrocław – uchwała budżetowa",
                "published_at": "2024-03-14",
                "content": "W czwartek 14 marca 2024 r. Rada Miasta Wrocławia przyjęła uchwałę "
                "budżetową na 2024 rok (25 głosów za, 10 przeciw).",
            }
        ],
    },
    "stary_news_jako_nowy": {
        "text": "PILNE! Właśnie zawalił się most na Wiśle w Toruniu, są ranni. Dziś w środę 12 marca "
        "2024 służby zamknęły cały rejon.",
        "article_date": date(2024, 3, 12),
        "sources": [
            {
                "id": "pap-2019",
                "title": "PAP: katastrofa mostu w Toruniu",
                "published_at": "2019-06-04",
                "content": "Wczoraj wieczorem zawaliło się przęsło mostu na Wiśle w Toruniu. "
                "Trzy osoby zostały ranne. Służby zamknęły rejon mostu.",
            }
        ],
    },
}


async def _run(names: list[str]) -> None:
    try:
        for name in names:
            ex = EXAMPLES[name]
            result = await analyze_async(ex["text"], ex["sources"], ex.get("article_date"))
            print(f"\n===== {name} =====")
            print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    finally:
        await reset_clients()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    names = sys.argv[1:] or list(EXAMPLES)
    unknown = [n for n in names if n not in EXAMPLES]
    if unknown:
        sys.exit(f"Nieznane przykłady: {unknown}. Dostępne: {', '.join(EXAMPLES)}")
    asyncio.run(_run(names))


if __name__ == "__main__":
    main()
