"""Read-only file/catalog responses confined to one explicitly configured data root."""
import hashlib
import json
import os
from pathlib import Path
import stat
from urllib.parse import unquote

DATA_ROUTE = "/api/data"


def is_data_route(path):
    return path == DATA_ROUTE or path.startswith(DATA_ROUTE + "/")


def resolve_data_path(root, route):
    relative = unquote(route[len(DATA_ROUTE):]).strip("/")
    if "\x00" in relative or "\\" in relative or any(p in (".", "..") for p in relative.split("/")):
        raise PermissionError("Caminho inválido")
    root = Path(root).resolve(strict=True)
    target = (root / relative).resolve(strict=True)
    if not target.is_relative_to(root):
        raise PermissionError("Caminho fora da raiz")
    return root, target


def serve_data(handler, root, route, company, head_only=False):
    try:
        root, target = resolve_data_path(root, route)
        if target.is_dir():
            entries = []
            for child in sorted(target.iterdir(), key=lambda p: p.name.casefold()):
                resolved = child.resolve()
                if not resolved.is_relative_to(root):
                    continue
                info = child.stat()
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    continue
                entries.append({"name": child.name, "path": child.relative_to(root).as_posix(),
                                "kind": "directory" if child.is_dir() else "file",
                                "size": info.st_size if child.is_file() else None,
                                "modifiedAtNs": info.st_mtime_ns})
            payload = json.dumps({"company": company, "path": target.relative_to(root).as_posix(),
                                  "entries": entries}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            etag = '"' + hashlib.sha256(payload).hexdigest() + '"'
            if handler.headers.get("If-None-Match") == etag:
                handler.headers_for(304, etag)
                handler.end_headers()
                return
            handler.headers_for(200, etag)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.send_header("Content-Length", str(len(payload)))
            handler.end_headers()
            if not head_only:
                handler.wfile.write(payload)
            return
        if not target.is_file():
            return handler.error(404)
        with target.open("rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                return handler.error(404)
            revision = f"{info.st_ino}:{info.st_mtime_ns}:{info.st_size}".encode()
            etag = 'W/"' + hashlib.sha256(revision).hexdigest() + '"'
            if handler.headers.get("If-None-Match") == etag:
                handler.headers_for(304, etag)
                handler.end_headers()
                return
            handler.headers_for(200, etag)
            # Raw bytes preserve gzip/parquet/etc. All files are downloads, not executable pages.
            handler.send_header("Content-Type", "application/octet-stream")
            handler.send_header("Content-Disposition", "attachment")
            handler.send_header("Content-Length", str(info.st_size))
            handler.end_headers()
            if not head_only:
                remaining = info.st_size
                while remaining:
                    chunk = stream.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    handler.wfile.write(chunk)
                    remaining -= len(chunk)
    except FileNotFoundError:
        handler.error(404)
    except PermissionError:
        handler.error(403)
    except (OSError, RuntimeError, ValueError):
        handler.error(503)
