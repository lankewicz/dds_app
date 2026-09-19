import gzip
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "monitor"))

from monitor.services.dds_control_projection import load_daily_projection
from monitor.services.turnos_service import _deserialize_day_cache


class DdsControlProjectionTests(unittest.TestCase):
    def test_reads_gzip_daily_projection(self):
        payload = {
            "schemaVersion": 1,
            "date": "2026-09-15",
            "teams": {"E3T01": {"completedAt": "2026-09-15T07:42:00-03:00"}},
        }
        blob = Mock()
        blob.download_as_bytes.return_value = gzip.compress(json.dumps(payload).encode("utf-8"))
        bucket = Mock()
        bucket.blob.return_value = blob
        client = Mock()
        client.bucket.return_value = bucket

        with patch("monitor.services.dds_control_projection._client", return_value=client):
            self.assertEqual(load_daily_projection("2026-09-15"), payload)

    def test_rejects_projection_for_another_day(self):
        blob = Mock()
        blob.download_as_bytes.return_value = json.dumps({"date": "2026-09-14"}).encode("utf-8")
        bucket = Mock()
        bucket.blob.return_value = blob
        client = Mock()
        client.bucket.return_value = bucket

        with patch("monitor.services.dds_control_projection._client", return_value=client):
            self.assertIsNone(load_daily_projection("2026-09-15"))

    def test_daily_projection_becomes_monitor_presence(self):
        entry = _deserialize_day_cache({
            "date": "2026-09-15",
            "teams": {
                "E3T01": {"completedAt": "2026-09-15T07:42:00-03:00"},
                "E3T02": {"completedAt": "2026-09-15T08:05:00-03:00"},
            },
        })
        self.assertEqual(entry["present"], {"E3T01", "E3T02"})
        self.assertEqual(entry["team_timestamps"]["E3T01"].hour, 10)
        self.assertFalse(entry["team_photos"])


if __name__ == "__main__":
    unittest.main()
