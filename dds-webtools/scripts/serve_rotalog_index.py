"""Servidor de um único arquivo, restrito ao IP Tailscale do Orange Pi."""

from __future__ import annotations

import argparse
import gzip
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def make_handler(index_path: Path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/api/monitor/turnos":
                self.send_error(404)
                return
            try:
                raw = index_path.read_bytes()
                payload = gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
                parsed = json.loads(payload.decode("utf-8-sig"))
                if not isinstance(parsed, dict) or not isinstance(parsed.get("equipes", parsed.get("snapshots")), dict):
                    raise ValueError("Índice inválido")
            except (OSError, ValueError, EOFError):
                self.send_error(503, "Index unavailable")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/gzip" if raw.startswith(b"\x1f\x8b") else "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="100.106.248.106")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--index", type=Path, default=Path("/home/orangepi/dds-coletor-rtl/dados-local/rotalog/equipes/current/index.json.gz"))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.index))
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
