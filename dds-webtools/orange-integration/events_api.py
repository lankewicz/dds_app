"""Authenticated read-only event endpoint, bound to loopback behind Tailscale Funnel."""
import argparse
import gzip
import hashlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import zlib

from rotalog_event_contract import validate_window
from torre_access import validate_token
from data_routes import is_data_route, serve_data
from data_roots import DataRoots

EVENT_ROUTE = "/api/rotalog/events"


def create_handler(events_file, key, company, origins, data_root=None, fallback_root=None,
                   ssd_mount=None, ssd_uuid=None):
    events_file = Path(events_file).resolve()
    roots = DataRoots(data_root, fallback_root, ssd_mount, ssd_uuid) if data_root is not None else None
    events_relative = events_file.relative_to(Path(data_root).resolve()) if roots else None

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log credentials, headers, or operational data.

        def headers_for(self, status, etag=None):
            self.send_response(status)
            self.send_header("Cache-Control", "private, no-cache" if status in (200, 304) else "no-store")
            self.send_header("Vary", "Origin, Authorization")
            self.send_header("X-Content-Type-Options", "nosniff")
            if self.headers.get("Origin") in origins:
                self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Access-Control-Expose-Headers", "ETag, X-Data-Source")
            if getattr(self, "data_source", None):
                self.send_header("X-Data-Source", self.data_source)
            if etag:
                self.send_header("ETag", etag)

        def error(self, status):
            self.headers_for(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(json.dumps({"ok": False, "status": status}).encode())

        def do_OPTIONS(self):
            requested = {v.strip().lower() for v in self.headers.get("Access-Control-Request-Headers", "").split(",") if v.strip()}
            path = urlsplit(self.path).path
            known = path == EVENT_ROUTE or (data_root is not None and is_data_route(path))
            if (not known or self.headers.get("Origin") not in origins
                    or self.headers.get("Access-Control-Request-Method") not in ("GET", "HEAD")
                    or not requested.issubset({"authorization", "if-none-match"})):
                return self.error(403)
            self.headers_for(204)
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD")
            self.send_header("Access-Control-Allow-Headers", "Authorization, If-None-Match")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()

        def do_GET(self):
            self.read_response()

        def do_HEAD(self):
            self.read_response(head_only=True)

        def do_POST(self):
            self.error(405)

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

        def read_response(self, head_only=False):
            path = urlsplit(self.path).path
            if path != EVENT_ROUTE and not (data_root is not None and is_data_route(path)):
                return self.error(404)
            if self.headers.get("Origin") and self.headers["Origin"] not in origins:
                return self.error(403)
            auth = self.headers.get("Authorization", "")
            try:
                if not auth.startswith("Bearer "):
                    raise ValueError("Ausente")
                validate_token(auth[7:], key, company)
            except ValueError:
                return self.error(401)
            selected_file = events_file
            if roots:
                try:
                    selected_root, self.data_source = roots.select()
                except (OSError, ValueError, RuntimeError):
                    return self.error(503)
                if is_data_route(path):
                    return serve_data(self, selected_root, path, company, head_only)
                selected_file = selected_root / events_relative
            try:
                with gzip.open(selected_file, "rb") as stream:
                    data = validate_window(json.loads(stream.read().decode("utf-8")), company)
                payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            except (OSError, EOFError, zlib.error, ValueError, TypeError):
                return self.error(503)
            etag = '"' + hashlib.sha256(payload).hexdigest() + '"'
            if self.headers.get("If-None-Match") == etag:
                self.headers_for(304, etag)
                self.end_headers()
                return
            self.headers_for(200, etag)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if not head_only:
                self.wfile.write(payload)

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events-file", required=True)
    parser.add_argument("--port", type=int, default=8082)
    parser.add_argument("--data-root", help="Raiz opcional de arquivos, exposta somente para leitura autenticada")
    parser.add_argument("--fallback-root")
    parser.add_argument("--ssd-mount")
    parser.add_argument("--ssd-uuid")
    args = parser.parse_args()
    key = os.environ.get("TORRE_SIGNING_KEY", "")
    company = os.environ.get("DDS_EMPRESA_PADRAO", "")
    origins = {s.strip() for s in os.environ.get("TORRE_ALLOWED_ORIGINS", "").split(",") if s.strip()}
    if len(key.encode()) < 32 or not company or not origins or any(urlsplit(v).scheme != "https" or not urlsplit(v).netloc or urlsplit(v).path not in ("", "/") for v in origins):
        raise SystemExit("Configurar chave, empresa e origens HTTPS antes de iniciar")
    if not Path(args.events_file).is_absolute():
        raise SystemExit("O arquivo de eventos precisa ter caminho absoluto")
    for value in (args.data_root, args.fallback_root, args.ssd_mount):
        if value and not Path(value).is_absolute():
            raise SystemExit("As raízes de dados precisam ter caminhos absolutos")
    ThreadingHTTPServer(("127.0.0.1", args.port), create_handler(args.events_file, key, company, origins,
        args.data_root, args.fallback_root, args.ssd_mount, args.ssd_uuid)).serve_forever()


if __name__ == "__main__":
    main()
