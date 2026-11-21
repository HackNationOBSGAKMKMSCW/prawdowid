"""Samodzielny serwer maskowania: ``python -m dataMasking [--host 127.0.0.1] [--port 8000]``.

Domyślnie przeładowuje się sam po zmianie plików (``git pull`` nie wymaga restartu);
``--no-reload`` to wyłącza.
"""

import argparse
from pathlib import Path

import uvicorn

from .api import RULES_VERSION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true", help="nie przeładowuj po zmianach")
    args = parser.parse_args()
    print(
        f"[dataMasking] reguły {RULES_VERSION}, nasłuchuję na "
        f"http://{args.host}:{args.port}/api/masking",
        flush=True,
    )
    uvicorn.run(
        "dataMasking.api:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        reload_dirs=[str(Path(__file__).parent)],
    )


if __name__ == "__main__":
    main()
