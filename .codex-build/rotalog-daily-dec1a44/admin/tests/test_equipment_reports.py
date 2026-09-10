import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
from flask import Flask
from jinja2 import DictLoader, ChoiceLoader

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("equipment_reports", ROOT / "equipment_reports.py")
reports = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reports)

class ReportTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(ROOT / "templates"))
        self.app.jinja_loader = ChoiceLoader([DictLoader({"base.html": "{% block content %}{% endblock %}"}), self.app.jinja_loader])
        self.app.add_url_rule("/reports", endpoint="admin.dds_reports", view_func=lambda: "")
        self.app.add_url_rule("/equipment", view_func=reports.report)
        self.service = types.ModuleType("monitor.services.teams_service")
        self.service.COLLECTION_NAME = "dds_teams"
        self.service.EQUIPMENT_HISTORY_SUBCOLLECTION = "equipment_history"
        self.service.list_teams_map = lambda active=None: {
            "E1": {"active": True, "displayName": "<Equipe>", "equipment": {"tablet": {"identifier": "CA001"}}},
            "E2": {"active": False, "equipment": {}}}
        self.service.db = self
        self.filters = []
        self.patcher = patch.dict(sys.modules, {"monitor.services.teams_service": self.service})
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = self.app.test_client()
    def collection(self, key): return self
    def document(self, key): return self
    def where(self, field, op, value):
        self.filters.append((field, op, value))
        return self
    def stream(self):
        return [types.SimpleNamespace(to_dict=lambda: {"equipmentType": "tablet", "changedAt": datetime(2026, 9, 10, 2, 59, tzinfo=timezone.utc), "before": {}, "after": {"identifier": "CA002"}, "changedByName": "Operador", "changeReason": "Troca"})]
    def test_current_and_html_escaping(self):
        response = self.client.get("/equipment")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"CA001", response.data)
        self.assertIn(b"&lt;Equipe&gt;", response.data)
        self.assertNotIn(b"<Equipe>", response.data)
        self.assertNotIn(b"<td>E2</td>", response.data)
    def test_missing_and_kind(self):
        data = self.client.get("/equipment?mode=missing&equipment=tablet&active=all&export=csv").get_data(as_text=True)
        self.assertIn("E2", data)
        self.assertNotIn("E1", data)
    def test_team_filter(self):
        data = self.client.get("/equipment?team=E2&active=all&export=csv").get_data(as_text=True)
        self.assertIn("E2", data)
        self.assertNotIn("E1", data)
    def test_history_period_and_timezone(self):
        response = self.client.get("/equipment?mode=history&start_date=2026-09-09&end_date=2026-09-09")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"09/09/2026 23:59:00", response.data)
        self.assertEqual(self.filters[0][2].hour, 0)
        self.assertEqual(self.filters[1][2].day, 10)
        self.assertEqual(self.filters[1][1], "<")
    def test_invalid_filters(self):
        for query in ("mode=invalid", "equipment=invalid", "start_date=2026-09-10&end_date=2026-09-09"):
            self.assertEqual(self.client.get("/equipment?" + query).status_code, 400)
    def test_csv_safety(self):
        self.assertIn("'=SUM(A1)", reports.csv_content(["a"], [["=SUM(A1)"]]))
    def test_failure_is_not_empty_report(self):
        self.service.list_teams_map = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("offline"))
        self.assertEqual(self.client.get("/equipment?export=csv").status_code, 503)

if __name__ == "__main__":
    unittest.main()
