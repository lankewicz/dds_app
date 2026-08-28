import copy
import datetime
import gzip
import json
import unittest

from boletim_x_ponto.services.rotalog_team_file_repository import (
    LOCAL_TZ,
    RotalogTeamFileRepository,
    merge_daily_document,
)


class MemoryStore:
    enabled = True

    def __init__(self):
        self.json = {}
        self.binary = {}

    def save_blob(self, name, payload):
        self.json[name] = copy.deepcopy(payload)

    def load_blob(self, name):
        return copy.deepcopy(self.json.get(name, {}))

    def list_blob_names(self, prefix):
        return sorted(name for name in self.json if name.startswith(prefix))

    def upload_bytes(self, name, payload, content_type):
        self.binary[name] = (payload, content_type)


class RotalogTeamFileRepositoryTests(unittest.TestCase):
    def test_lifecycle_enrichment_keeps_one_service(self):
        base = {
            "teamKey": "E3389", "updatedAtIso": "2026-08-27T15:40:00-03:00",
            "estadoConsolidado": "ABERTO", "turno": {}, "intervalos": [],
            "ssExecutadas": [],
            "ssEmAndamento": [{"tipo": "9925", "inicioIso": "2026-08-27T15:37:00-03:00", "inicioDeslocamento": "15:37"}],
        }
        daily = merge_daily_document(None, base, "2026-08-27")
        enriched = copy.deepcopy(base)
        enriched["ssEmAndamento"][0].update({"inicioExecucao": "16:02", "protocolo": "20265453323251"})
        daily = merge_daily_document(daily, enriched, "2026-08-27")
        self.assertEqual(1, len(daily["services"]))
        self.assertEqual("20265453323251", daily["services"][0]["protocolo"])

    def test_multiple_intervals_are_preserved(self):
        current = {
            "teamKey": "E3389", "estadoConsolidado": "ABERTO", "turno": {},
            "ssExecutadas": [], "ssEmAndamento": [],
            "intervalos": [
                {"inicioIso": "2026-08-27T10:00:00-03:00", "fimIso": "2026-08-27T10:15:00-03:00"},
                {"inicioIso": "2026-08-27T14:00:00-03:00", "fimIso": "2026-08-27T14:20:00-03:00"},
            ],
        }
        daily = merge_daily_document(None, current, "2026-08-27")
        self.assertEqual(2, len(daily["turno"]["intervalos"]))

    def test_turn_check_runs_first_time_after_06_even_after_restart(self):
        store = MemoryStore()
        repo = RotalogTeamFileRepository(store)
        before = datetime.datetime(2026, 8, 27, 5, 59, tzinfo=LOCAL_TZ)
        self.assertEqual("scheduled_for_06:00", repo.record_daily_turn_check(90, before)["reason"])
        late_start = datetime.datetime(2026, 8, 27, 10, 30, tzinfo=LOCAL_TZ)
        self.assertTrue(repo.record_daily_turn_check(95, late_start)["executed"])
        restarted = RotalogTeamFileRepository(store)
        result = restarted.record_daily_turn_check(95, late_start.replace(hour=14))
        self.assertFalse(result["executed"])
        self.assertEqual("already_checked_today", result["reason"])
    def test_monthly_runs_only_once_after_04_even_after_restart(self):
        store = MemoryStore()
        repo = RotalogTeamFileRepository(store)
        before = datetime.datetime(2026, 8, 27, 3, 59, tzinfo=LOCAL_TZ)
        self.assertEqual("scheduled_for_04:00", repo.consolidate_month_once_per_day(before)["reason"])
        after = datetime.datetime(2026, 8, 27, 4, 0, tzinfo=LOCAL_TZ)
        self.assertTrue(repo.consolidate_month_once_per_day(after)["executed"])
        restarted = RotalogTeamFileRepository(store)
        result = restarted.consolidate_month_once_per_day(after.replace(hour=12))
        self.assertFalse(result["executed"])
        self.assertEqual("already_built_today", result["reason"])
        self.assertEqual(2, len(store.binary))


if __name__ == "__main__":
    unittest.main()