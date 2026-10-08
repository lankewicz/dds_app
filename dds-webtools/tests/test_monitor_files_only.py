import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "monitor"))
sys.path.insert(0, str(ROOT))

from monitor.services import turnos_service as service


class MonitorFilesOnlyTests(unittest.TestCase):
    def test_manual_and_automatic_refresh_use_files_without_source_queries(self):
        now = datetime(2026, 10, 6, 10, tzinfo=ZoneInfo("America/Sao_Paulo"))
        today_entry = {"completedAt": "2026-10-06T07:30:00-03:00"}
        projections = (["2026-10-06"], {
            "2026-10-06": {"teams": {"DDS01": today_entry}},
        })
        for manual in (False, True):
            with self.subTest(manual=manual), \
                 patch.object(service, "_read_monitor_view_cache", side_effect=lambda company: service._MONITOR_VIEW_CACHE.get(company, {"items": []})), \
                 patch.object(service, "_get_now", return_value=now), \
                 patch.object(service, "_rotalog_json_snapshots", return_value={}) as snapshots, \
                 patch("monitor.services.dds_control_projection.sync_recent_daily_projections", return_value=projections) as daily, \
                 patch.object(service, "list_teams_map", side_effect=AssertionError("Cadastro Firestore consultado")), \
                 patch.object(service, "_load_today_dds_teams", side_effect=AssertionError("DDS fonte consultado")), \
                 patch.object(service, "_load_recent_7d_dds_teams", side_effect=AssertionError("Histórico fonte consultado")), \
                 patch.object(service, "_claim_monitor_cache_refresh", side_effect=AssertionError("Trava Firestore consultada")), \
                 patch.object(service, "_write_monitor_view_cache", side_effect=AssertionError("Arquivo escrito")):
                result = service.list_turnos("ChicoEletro", files_only=True, manual_refresh=manual)
                self.assertEqual(result["dataSource"], "monitor_files")
                self.assertEqual(result["items"][0]["teamKey"], "DDS01")
                self.assertEqual(result["items"][0]["estado"], "ABERTO")
                self.assertEqual(result["items"][0]["ddsToday"], "ok")
                snapshots.assert_called_once_with(force=True)
                daily.assert_called_once_with(limit_days=25, manual_refresh=True)
                history = service.list_turnos_dds("ChicoEletro")
                self.assertEqual(history["items"][0]["ddsToday"], "ok")
                self.assertEqual(snapshots.call_count, 1)
                self.assertEqual(daily.call_count, 1)


if __name__ == "__main__":
    unittest.main()
