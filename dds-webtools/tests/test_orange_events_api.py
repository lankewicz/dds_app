import gzip
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orange-integration"))
from torre_access import issue_token

spec = importlib.util.spec_from_file_location("events_api", ROOT / "orange-integration/events_api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
KEY = "k" * 40
ORIGIN = "https://chicoeletro.web.app"


class OrangeEventsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "index.json.gz"
        self.payload = {"schemaVersion": 1, "company": "ChicoEletro", "timezone": "America/Sao_Paulo",
            "windowHours": 24, "updatedAt": "2026-10-20T08:00:00-03:00", "items": []}
        self.write(self.payload)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.server_handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)
        self.auth = {"Origin": ORIGIN, "Authorization": "Bearer " + issue_token(KEY, "ChicoEletro", "user")}

    def server_handler(self):
        return api.create_handler(self.path, KEY, "ChicoEletro", {ORIGIN})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def write(self, payload):
        self.path.write_bytes(gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8")))

    def request(self, path="/api/rotalog/events", headers=None, method="GET"):
        try:
            return urlopen(Request(self.url + path, headers=headers or {}, method=method), timeout=3)
        except HTTPError as exc:
            return exc

    def test_empty_window_cors_and_conditional_auth(self):
        with self.request(headers=self.auth) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response), self.payload)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], ORIGIN)
            etag = response.headers["ETag"]
        for headers, status in [({}, 401), ({"If-None-Match": etag}, 401),
                                ({**self.auth, "If-None-Match": etag}, 304)]:
            with self.request(headers=headers) as response:
                self.assertEqual(response.status, status)

    def test_only_allowed_read_route_and_origin(self):
        with self.request("/.env", self.auth) as response:
            self.assertEqual(response.status, 404)
        with self.request(headers={**self.auth, "Origin": "https://other.test"}) as response:
            self.assertEqual(response.status, 403)
        with self.request(headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET",
                                  "Access-Control-Request-Headers": "authorization,if-none-match"}, method="OPTIONS") as response:
            self.assertEqual(response.status, 204)
        with self.request(headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"}, method="OPTIONS") as response:
            self.assertEqual(response.status, 403)
        with self.request(headers=self.auth, method="POST") as response:
            self.assertEqual(response.status, 405)

    def test_wrong_company_and_bad_dates_do_not_escape(self):
        item = {"id": "one", "teamKey": "T1", "entityId": "service", "type": "C", "protocol": "20265804191700",
                "status": "EXECUCAO", "occurredAt": "2026-02-30T08:00:00-03:00", "timeSource": "consolidated"}
        for data in [{**self.payload, "company": "Outra"}, {**self.payload, "schemaVersion": 2},
                     {**self.payload, "items": [item]}]:
            self.write(data)
            with self.request(headers=self.auth) as response:
                self.assertEqual(response.status, 503)
        self.path.write_bytes(b"corrupt gzip")
        with self.request(headers=self.auth) as response:
            self.assertEqual(response.status, 503)
        self.path.unlink()
        with self.request(headers=self.auth) as response:
            self.assertEqual(response.status, 503)

    def test_file_replacements_keep_only_producer_events(self):
        item = {"id": "one", "teamKey": "T1", "entityId": "service", "type": "C", "protocol": "20265804191700",
                "status": "EXECUCAO", "occurredAt": "2026-10-20T08:00:00-03:00", "timeSource": "consolidated"}
        for events in [[item], [{**item, "occurredAt": "2026-10-20T08:05:00-03:00"}], []]:
            self.write({**self.payload, "items": events})
            with self.request(headers=self.auth) as response:
                self.assertEqual(json.load(response)["items"], events)


class OrangeReadOnlyDataTests(OrangeEventsTests):
    def server_handler(self):
        self.primary = Path(self.tmp.name) / "ssd"
        self.fallback = Path(self.tmp.name) / "local"
        self.primary.mkdir()
        self.fallback.mkdir()
        self.path = self.primary / "rotalog/events/current/index.json.gz"
        self.path.parent.mkdir(parents=True)
        self.write(self.payload)
        self.file = self.primary / "sample.json.gz"
        self.file.write_bytes(gzip.compress(b'{"source":"ssd"}'))
        (self.fallback / self.file.name).write_bytes(gzip.compress(b'{"source":"local"}'))
        return api.create_handler(self.path, KEY, "ChicoEletro", {ORIGIN}, self.primary, self.fallback)

    def test_catalog_raw_download_and_head_require_authorization(self):
        with self.request("/api/data") as response:
            self.assertEqual(response.status, 401)
        with self.request("/api/data", self.auth) as response:
            data = json.load(response)
            self.assertEqual(data["company"], "ChicoEletro")
            self.assertIn("sample.json.gz", [entry["name"] for entry in data["entries"]])
            self.assertEqual(response.headers["X-Data-Source"], "ssd")
        with self.request("/api/data/sample.json.gz", self.auth) as response:
            self.assertEqual(response.read(), self.file.read_bytes())
            self.assertEqual(response.headers["Content-Disposition"], "attachment")
            etag = response.headers["ETag"]
        with self.request("/api/data/sample.json.gz", self.auth, "HEAD") as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b"")
            self.assertEqual(int(response.headers["Content-Length"]), self.file.stat().st_size)
        with self.request("/api/data/sample.json.gz", {**self.auth, "If-None-Match": etag}) as response:
            self.assertEqual(response.status, 304)
        with self.request("/api/data/sample.json.gz", {"If-None-Match": etag}) as response:
            self.assertEqual(response.status, 401)

    def test_all_mutation_methods_are_rejected_without_changes(self):
        before = self.file.read_bytes()
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.request("/api/data/sample.json.gz", self.auth, method) as response:
                self.assertEqual(response.status, 405)
        self.assertEqual(self.file.read_bytes(), before)

    def test_traversal_and_wrong_company_denied(self):
        (Path(self.tmp.name) / "outside.txt").write_text("private")
        for path in ("/api/data/%2e%2e/outside.txt", "/api/data/..%2foutside.txt", "/api/data/%5c..%5coutside.txt"):
            with self.request(path, self.auth) as response:
                self.assertEqual(response.status, 403)
        wrong = {**self.auth, "Authorization": "Bearer " + issue_token(KEY, "Outra", "user")}
        with self.request("/api/data", wrong) as response:
            self.assertEqual(response.status, 401)

    def test_symlink_cannot_escape_root(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("private")
        try:
            (self.primary / "escape.txt").symlink_to(outside)
        except OSError:
            self.skipTest("O sistema não permite criar links simbólicos nesta sessão")
        with self.request("/api/data/escape.txt", self.auth) as response:
            self.assertEqual(response.status, 403)
        with self.request("/api/data", self.auth) as response:
            self.assertNotIn("escape.txt", [entry["name"] for entry in json.load(response)["entries"]])

    def test_fallback_only_when_ssd_is_offline(self):
        self.file.unlink()
        with self.request("/api/data/sample.json.gz", self.auth) as response:
            self.assertEqual(response.status, 404)  # Local file exists but SSD is online.
        with patch.object(api.DataRoots, "ssd_available", return_value=False):
            with self.request("/api/data/sample.json.gz", self.auth) as response:
                self.assertEqual(json.loads(gzip.decompress(response.read())), {"source": "local"})
                self.assertEqual(response.headers["X-Data-Source"], "local")
        with self.request("/api/data/sample.json.gz", self.auth) as response:
            self.assertEqual(response.status, 404)  # SSD takes precedence again immediately.

    def test_missing_primary_root_is_not_treated_as_offline(self):
        roots = api.DataRoots(self.primary / "missing", self.fallback)
        with self.assertRaises(FileNotFoundError):
            roots.select()
        with patch.object(roots, "ssd_available", return_value=False):
            self.assertEqual(roots.select(), (self.fallback.resolve(), "local"))


if __name__ == "__main__":
    unittest.main()
