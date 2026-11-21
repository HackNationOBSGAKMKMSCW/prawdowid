"""Run the adapter server: ``python -m whatsappAdapter [--demo] [--port 8000]``."""

import argparse
import os

import uvicorn
from observability import init as init_logging

from .server import MODE_ENV, create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="SprawdzTo WhatsApp adapter (simulator backend)")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="answer from built-in example data, without API keys or network",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.demo:
        os.environ[MODE_ENV] = "demo"
    init_logging()
    app = create_app()
    print(
        f"[whatsappAdapter] Tryb: {os.getenv(MODE_ENV, 'live')}; "
        f"nasłuchuję na http://{args.host}:{args.port}",
        flush=True,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
