import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "monitor"))
sys.path.insert(0, str(ROOT))

from monitor.services import turnos_activity_service as service


class StatusFeedTests(unittest.TestCase):
    def test_closed_without_real_end_time_is_only_a_snapshot(self):
        item = {"teamKey": "T1", "estado": "FECHADO",
                "turnoFim": "2026-10-08T18:00:00-03:00",
                "updatedAt": "2026-10-08T18:00:00-03:00",
                "rotalogSnapshot": {"turno": {"status": "FECHADO"}}}
        with patch.object(service, "_read_monitor_view_cache", return_value={"items": [item]}):
            first = service.get_activity_feed()["items"][0]
            item["updatedAt"] = "2026-10-08T18:05:00-03:00"
            second = service.get_activity_feed()["items"][0]
        self.assertTrue(first["snapshotOnly"])
        self.assertIsNone(first["activityAt"])
        self.assertEqual(first["eventId"], second["eventId"])

    def test_real_closure_keeps_timestamp_across_scrapes(self):
        end = "2026-10-08T17:00:00-03:00"
        item = {"teamKey": "T1", "estado": "FECHADO",
                "updatedAt": "2026-10-08T18:00:00-03:00",
                "rotalogSnapshot": {"turno": {"fim": end}}}
        with patch.object(service, "_read_monitor_view_cache", return_value={"items": [item]}):
            first = service.get_activity_feed()["items"][0]
            item["updatedAt"] = "2026-10-08T18:05:00-03:00"
            second = service.get_activity_feed()["items"][0]
        self.assertFalse(first["snapshotOnly"])
        self.assertEqual(first["time"], "17:00")
        self.assertEqual(first["eventId"], second["eventId"])

    def test_team_and_service_transitions_are_separate_and_deduplicated(self):
        order = {
            "protocolo": "50961067", "status": "CONCLUSAO",
            "transitions": [
                {"status": "DESLOCAMENTO", "hora": "08:00"},
                {"status": "EXECUCAO", "hora": "08:15"},
                {"status": "CONCLUSAO", "hora": "09:00"},
            ],
        }
        cache = {"items": [{
            "teamKey": "E2146", "estado": "ABERTO",
            "origemAtualizacao": "TORRE_CONTROLE",
            "turnoInicio": "2026-10-07T07:00:00-03:00",
            "updatedAt": "2026-10-07T09:05:00-03:00",
            "rotalogSnapshot": {
                "date": "2026-10-07",
                "fila": {"comercial": 3, "emergencia": 2},
                "ordensServico": {"atual": order, "historico": [order]},
            },
        }]}
        with patch.object(service, "_read_monitor_view_cache", return_value=cache):
            result = service.get_activity_feed("ChicoEletro")
        self.assertEqual([(e["time"], e["label"]) for e in result["items"] if not e.get("snapshotOnly")], [
            ("09:00", "SS 50961067: Conclusão"),
            ("08:15", "SS 50961067: Execução"),
            ("08:00", "SS 50961067: Deslocamento"),
            ("07:00", "Equipe: Turno Aberto"),
        ])
        self.assertEqual(result["summary"]["comerciais"], 3)


if __name__ == "__main__":
    unittest.main()
