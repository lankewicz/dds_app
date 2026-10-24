"""Verify the installed API without modifying any collector data or printing credentials."""
import gzip
import json
from pathlib import Path
import sys
import tempfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, ProxyHandler, build_opener

from torre_access import issue_token
from data_routes import resolve_data_path


def main():
    settings = dict(line.split("=", 1) for line in Path(".env").read_text().splitlines() if "=" in line and not line.startswith("#"))
    company = settings["DDS_EMPRESA_PADRAO"]
    key = settings["TORRE_SIGNING_KEY"]
    origin = "https://chicoeletro.web.app"
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8082"
    token = issue_token(key, company, "read-only-verification")
    opener = build_opener(ProxyHandler({}))

    def request(path, method="GET", auth=True, extra=None):
        headers = {"Origin": origin}
        if auth:
            headers["Authorization"] = "Bearer " + token
        headers.update(extra or {})
        try:
            return opener.open(Request(base + path, headers=headers, method=method), timeout=15)
        except HTTPError as exc:
            return exc

    result = {}
    with request("/api/data", auth=False) as response:
        assert response.status == 401
        result["anonymous"] = response.status
    with request("/api/data") as response:
        assert response.status == 200
        assert json.load(response)["company"] == company
        result["catalog"] = response.status
        result["source"] = response.headers.get("X-Data-Source")
    path = "/api/data/rotalog/equipes/current/index.json.gz"
    with request(path) as response:
        assert response.status == 200
        raw = response.read()
        assert isinstance(json.loads(gzip.decompress(raw)), dict)
        result["downloadBytes"] = len(raw)
    with request(path, method="HEAD") as response:
        assert response.status == 200 and response.read() == b""
        result["head"] = response.status
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        with request("/api/data", method=method) as response:
            assert response.status == 405
    result["mutationsBlocked"] = True
    with request("/api/data/%2e%2e/.env") as response:
        assert response.status == 403
        result["traversalBlocked"] = True
    wrong = issue_token(key, "Outra", "read-only-verification")
    with request("/api/data", extra={"Authorization": "Bearer " + wrong}) as response:
        assert response.status == 401
        result["companyIsolation"] = True
    with request("/api/data", method="OPTIONS", auth=False, extra={
        "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}) as response:
        assert response.status == 204 and response.headers["Access-Control-Allow-Origin"] == origin
        result["cors"] = response.status
    with request("/api/rotalog/events") as response:
        result["eventsStatus"] = response.status
    # Actual Linux symlink test, entirely in temporary test fixtures.
    with tempfile.TemporaryDirectory() as directory:
        parent = Path(directory)
        root = parent / "root"
        root.mkdir()
        outside = parent / "outside"
        outside.write_text("test fixture")
        (root / "escape").symlink_to(outside)
        try:
            resolve_data_path(root, "/api/data/escape")
        except PermissionError:
            result["symlinkEscapeBlocked"] = True
        else:
            raise AssertionError("Link saiu da raiz autorizada")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
