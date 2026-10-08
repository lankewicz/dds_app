import gzip
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bdo.services.rotalog_monitor_source import load_monitor_index
from scripts.serve_rotalog_index import make_handler


class MonitorSourceTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"schemaVersion": 3, "equipes": {"E01": {"teamKey": "E01"}}}
        self.env = patch.dict(os.environ, {"ROTALOG_ORANGE_INDEX_URL": "http://100.106.248.106:8766/api/monitor/turnos", "ROTALOG_ORANGE_PROXY": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_orange_success_does_not_read_firebase(self):
        fallback = Mock()
        response = Mock(status_code=200, content=gzip.compress(json.dumps(self.payload).encode()))
        with patch("bdo.services.rotalog_monitor_source.requests.Session") as session:
            session.return_value.__enter__.return_value.get.return_value = response
            self.assertEqual(load_monitor_index(fallback), (self.payload, "orangepi"))
            fallback.assert_not_called()

    def test_timeout_invalid_json_and_http_error_fall_back(self):
        failures = [TimeoutError(), Mock(status_code=503), Mock(status_code=200, content=b"invalid"), Mock(status_code=200, content=b"{\"equipes\": []}")]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), patch("bdo.services.rotalog_monitor_source.requests.Session") as session:
                get = session.return_value.__enter__.return_value.get
                if isinstance(failure, Exception):
                    get.side_effect = failure
                else:
                    get.return_value = failure
                fallback = Mock(return_value=self.payload)
                self.assertEqual(load_monitor_index(fallback), (self.payload, "firebase"))
                fallback.assert_called_once_with()

    def test_without_orange_configuration_reads_firebase(self):
        with patch.dict(os.environ, {"ROTALOG_ORANGE_INDEX_URL": ""}):
            self.assertEqual(load_monitor_index(lambda: self.payload), (self.payload, "firebase"))

    def test_empty_team_map_is_valid_and_firebase_failure_propagates(self):
        with patch.dict(os.environ, {"ROTALOG_ORANGE_INDEX_URL": ""}):
            empty = {"schemaVersion": 3, "equipes": {}}
            self.assertEqual(load_monitor_index(lambda: empty), (empty, "firebase"))
            with self.assertRaises(OSError):
                load_monitor_index(Mock(side_effect=OSError()))

    def test_live_endpoint_reads_file_and_falls_back_when_file_disappears(self):
        with tempfile.TemporaryDirectory() as directory:
            index = Path(directory) / "index.json.gz"
            index.write_bytes(gzip.compress(json.dumps(self.payload).encode()))
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(index))
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with patch.dict(os.environ, {"ROTALOG_ORANGE_INDEX_URL": f"http://127.0.0.1:{server.server_port}/api/monitor/turnos"}):
                    fallback = Mock(return_value=self.payload)
                    self.assertEqual(load_monitor_index(fallback)[1], "orangepi")
                    fallback.assert_not_called()
                    index.unlink()
                    self.assertEqual(load_monitor_index(fallback)[1], "firebase")
            finally:
                server.shutdown()
                server.server_close()
                worker.join()


if __name__ == "__main__":
    unittest.main()
