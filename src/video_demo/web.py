"""Read-only result viewer bound to the server loopback interface."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from .result_store import ResultStore


_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}
_RUN = re.compile(r"/api/runs/([^/]+)\Z")
_FILE = re.compile(r"/api/runs/([^/]+)/files/([^/]+)\Z")
_EVIDENCE = re.compile(r"/api/runs/([^/]+)/evidence/([^/]+)\Z")


def make_server(runs_dir: Path, port: int = 8765) -> ThreadingHTTPServer:
    store = ResultStore(runs_dir)
    assets = Path(__file__).parent / "web_assets"

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str, *, download: str | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'")
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, value: object) -> None:
            self._send(200, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self) -> None:
            route = unquote(urlsplit(self.path).path)
            if route in _ASSETS:
                filename, content_type = _ASSETS[route]
                try:
                    self._send(200, (assets / filename).read_bytes(), content_type)
                except OSError:
                    self._send(500, b"Asset unavailable", "text/plain; charset=utf-8")
                return
            try:
                if route == "/api/videos":
                    self._json(store.list_videos())
                elif match := _RUN.fullmatch(route):
                    self._json(store.get_run(match.group(1)))
                elif match := _FILE.fullmatch(route):
                    filename = match.group(2)
                    content_type = {
                        "result.json": "application/json; charset=utf-8",
                        "manifest.json": "application/json; charset=utf-8",
                        "summary.md": "text/markdown; charset=utf-8",
                    }.get(filename, "application/octet-stream")
                    self._send(200, store.read_file(match.group(1), filename), content_type, download=filename)
                elif match := _EVIDENCE.fullmatch(route):
                    filename = match.group(2)
                    extension = Path(filename).suffix.lower()
                    content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(extension, "application/octet-stream")
                    self._send(200, store.read_evidence(match.group(1), filename), content_type)
                else:
                    self._send(404, b"Not found", "text/plain; charset=utf-8")
            except (KeyError, OSError):
                self._send(404, b"Not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:
            self._send(405, b"Read-only server", "text/plain; charset=utf-8")

        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only local video result viewer")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    server = make_server(args.runs_dir, args.port)
    print(f"Serving results at http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
