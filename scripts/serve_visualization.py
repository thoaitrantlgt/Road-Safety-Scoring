from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8094
ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "data" / "processed" / "visualization" / "index.html"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the interactive geospatial visualization.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--check", action="store_true", help="Print the expected URL without starting the server.")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/data/processed/visualization/"
    if not MAP_PATH.exists():
        raise SystemExit(f"Map landing page not found: {MAP_PATH}")
    print(f"Map URL: {url}")
    print(f"Direct file URL: file:///{MAP_PATH.as_posix().replace(':', ':')}")
    if args.check:
        return

    handler = lambda *handler_args, **handler_kwargs: QuietHandler(  # noqa: E731
        *handler_args,
        directory=str(ROOT),
        **handler_kwargs,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print("Press Ctrl+C to stop the server.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
