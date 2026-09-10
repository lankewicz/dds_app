import copy
import datetime
import unittest

from bdo.services.rotalog_execution_log import RotalogExecutionLog
from bdo.services.rotalog_team_file_repository import LOCAL_TZ


class MemoryStore:
    def __init__(self):
        self.data = {}

    def update_blob(self, path, transform):
        value = transform(copy.deepcopy(self.data.get(path, {})))
        self.data[path] = copy.deepcopy(value)
        return value

    def load_blob(self, path):
        return copy.deepcopy(self.data.get(path, {}))


class RotalogExecutionLogTests(unittest.TestCase):
    def test_summarizes_success_and_skipped_attempts(self):
        store = MemoryStore()
        log = RotalogExecutionLog(store)
        start = datetime.datetime(2026, 9, 9, 6, 0, tzinfo=LOCAL_TZ)
        log.record("success", started_at=start, finished_at=start + datetime.timedelta(seconds=12), duration_seconds=10)
        result = log.record("skipped", started_at=start, finished_at=start, duration_seconds=0, details={"reason": "sync_already_running"})

        self.assertIn("dados/chicoeletro/rotalog/logs/2026-09-09.json.gz", store.data)
        self.assertEqual(2, result["summary"]["attempts"])
        self.assertEqual(1, result["summary"]["successes"])
        self.assertEqual(1, result["summary"]["skipped"])
        self.assertEqual(10, result["summary"]["averageDurationSeconds"])
        self.assertEqual(result, log.load("2026-09-09"))


if __name__ == "__main__":
    unittest.main()
