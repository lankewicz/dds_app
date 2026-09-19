import unittest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import sys
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
MONITOR_DIR = ROOT_DIR / "monitor"
if str(MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(MONITOR_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from monitor.services.turnos_service import _build_dds_controlled_items, _build_pure_torre_items, list_turnos, DDS_TIMEZONE


class TestDdsTurnoControl(unittest.TestCase):
    def setUp(self):
        self.tz = ZoneInfo("America/Sao_Paulo")
        self.sample_teams_map = {
            "E_SEM_TEL_1": {
                "displayName": "Equipe Sem Telemetria 1",
                "tablet": "TAB-01",
                "veiculo": "CAR-01",
                "members": ["JOAO SILVA", "MARIA SOUZA"],
                "setor": "COMERCIAL",
            },
            "E_SEM_TEL_2": {
                "displayName": "Equipe Sem Telemetria 2",
                "tablet": "TAB-02",
                "veiculo": "CAR-02",
                "members": ["CARLOS PEREIRA"],
                "setor": "EMERGENCIA",
            },
            "E_SEM_DDS": {
                "displayName": "Equipe Sem DDS Hoje",
                "tablet": "TAB-03",
                "veiculo": "CAR-03",
                "members": ["PEDRO SANTOS"],
                "setor": "COMERCIAL",
            },
        }

    def test_equipe_com_dds_antes_das_18_turno_aberto(self):
        # DDS realizado às 07:42, horário atual 10:30
        now_dt = datetime(2026, 9, 17, 10, 30, 0, tzinfo=self.tz)
        today_dds = {
            "E_SEM_TEL_1": {"completedAt": "2026-09-17T07:42:00-03:00"}
        }

        with patch("monitor.services.turnos_service.list_teams_map", return_value=self.sample_teams_map), \
             patch("monitor.services.turnos_service._load_today_dds_teams", return_value=today_dds):
            items = _build_dds_controlled_items(telemetry_keys=set(), now=now_dt)
            items_map = {it["teamKey"]: it for it in items}

            e1 = items_map["E_SEM_TEL_1"]
            self.assertEqual(e1["estado"], "ABERTO")
            self.assertEqual(e1["turnStatus"], "ABERTO")
            self.assertEqual(e1["turnoInicio"], "2026-09-17T07:42:00-03:00")
            self.assertIsNone(e1["turnoFim"])
            self.assertTrue(e1["active"])
            self.assertEqual(e1["origemAtualizacao"], "TORRE_DDS")
            self.assertEqual(e1["ddsToday"], "ok")

    def test_equipe_com_dds_apos_as_18_turno_fechado_automatico(self):
        # DDS realizado às 07:42, mas agora são 18:15 (fechamento automático)
        now_dt = datetime(2026, 9, 17, 18, 15, 0, tzinfo=self.tz)
        today_dds = {
            "E_SEM_TEL_1": {"completedAt": "2026-09-17T07:42:00-03:00"}
        }

        with patch("monitor.services.turnos_service.list_teams_map", return_value=self.sample_teams_map), \
             patch("monitor.services.turnos_service._load_today_dds_teams", return_value=today_dds):
            items = _build_dds_controlled_items(telemetry_keys=set(), now=now_dt)
            items_map = {it["teamKey"]: it for it in items}

            e1 = items_map["E_SEM_TEL_1"]
            self.assertEqual(e1["estado"], "FECHADO")
            self.assertEqual(e1["turnStatus"], "FECHADO")
            self.assertEqual(e1["turnoInicio"], "2026-09-17T07:42:00-03:00")
            self.assertEqual(e1["turnoFim"], "2026-09-17T18:00:00-03:00")
            self.assertTrue(e1["active"])
            self.assertEqual(e1["origemAtualizacao"], "TORRE_DDS")
            self.assertIn("Fechamento automático (18:00)", e1["motivo"])

    def test_equipe_enviou_dds_apos_as_18_permanece_fechado(self):
        # DDS realizado/enviado às 18:45, horário atual 19:00
        now_dt = datetime(2026, 9, 17, 19, 0, 0, tzinfo=self.tz)
        today_dds = {
            "E_SEM_TEL_2": {"completedAt": "2026-09-17T18:45:00-03:00"}
        }

        with patch("monitor.services.turnos_service.list_teams_map", return_value=self.sample_teams_map), \
             patch("monitor.services.turnos_service._load_today_dds_teams", return_value=today_dds):
            items = _build_dds_controlled_items(telemetry_keys=set(), now=now_dt)
            items_map = {it["teamKey"]: it for it in items}

            e2 = items_map["E_SEM_TEL_2"]
            self.assertEqual(e2["estado"], "FECHADO")
            self.assertEqual(e2["turnStatus"], "FECHADO")
            self.assertTrue(e2["active"])
            self.assertEqual(e2["turnoInicio"], "2026-09-17T18:45:00-03:00")
            self.assertEqual(e2["turnoFim"], "2026-09-17T18:45:00-03:00")

    def test_equipe_sem_dds_no_dia_permanece_fechada_e_inativa(self):
        now_dt = datetime(2026, 9, 17, 10, 0, 0, tzinfo=self.tz)
        today_dds = {}

        with patch("monitor.services.turnos_service.list_teams_map", return_value=self.sample_teams_map), \
             patch("monitor.services.turnos_service._load_today_dds_teams", return_value=today_dds):
            items = _build_dds_controlled_items(telemetry_keys=set(), now=now_dt)
            items_map = {it["teamKey"]: it for it in items}

            e_no_dds = items_map["E_SEM_DDS"]
            self.assertEqual(e_no_dds["estado"], "FECHADO")
            self.assertEqual(e_no_dds["turnStatus"], "FECHADO")
            self.assertFalse(e_no_dds["active"])
            self.assertIsNone(e_no_dds["turnoInicio"])
            self.assertIsNone(e_no_dds["turnoFim"])
            self.assertEqual(e_no_dds["ddsToday"], "neutral")

    def test_convivencia_mista_rotalog_e_dds_em_list_turnos(self):
        now_dt = datetime(2026, 9, 17, 11, 0, 0, tzinfo=self.tz)
        sample_snapshots = {
            "E_COM_TEL": {
                "teamKey": "E_COM_TEL",
                "date": "2026-09-17",
                "schemaVersion": 2,
                "jornada": {
                    "emIntervalo": False,
                    "turno": {"status": "ABERTO", "inicio": "2026-09-17T08:00:00-03:00"}
                },
                "ordensServico": {
                    "atual": {"protocolo": "SS-999", "statusAtual": "EXECUCAO"}
                }
            }
        }
        sample_dds = {
            "E_SEM_TEL_1": {"completedAt": "2026-09-17T07:42:00-03:00"}
        }

        with patch("monitor.services.turnos_service._rotalog_json_snapshots", return_value=sample_snapshots), \
             patch("monitor.services.turnos_service.list_teams_map", return_value=self.sample_teams_map), \
             patch("monitor.services.turnos_service._load_today_dds_teams", return_value=sample_dds), \
             patch("monitor.services.turnos_service._get_now", return_value=now_dt):
            res = list_turnos(empresa="ChicoEletro", active=True, manual_refresh=True)
            self.assertEqual(res["dataSource"], "torre_controle")
            items = res["items"]
            keys = [it["teamKey"] for it in items]

            # Ambas as equipes ativas devem estar presentes
            self.assertIn("E_COM_TEL", keys)
            self.assertIn("E_SEM_TEL_1", keys)

            items_map = {it["teamKey"]: it for it in items}
            # Equipe com telemetria operando reflete turno ABERTO e atividade EXECUCAO
            self.assertEqual(items_map["E_COM_TEL"]["estado"], "ABERTO")
            self.assertEqual(items_map["E_COM_TEL"]["turnStatus"], "ABERTO")
            self.assertEqual(items_map["E_COM_TEL"]["atividadeStatusRotalog"], "EXECUCAO")
            self.assertEqual(items_map["E_COM_TEL"]["origemAtualizacao"], "TORRE_CONTROLE")

            # Equipe sem telemetria reflete DDS (ABERTO)
            self.assertEqual(items_map["E_SEM_TEL_1"]["estado"], "ABERTO")
            self.assertEqual(items_map["E_SEM_TEL_1"]["origemAtualizacao"], "TORRE_DDS")

    def test_plantao_madrugada_e_dias_anteriores_fechados(self):
        """Equipe de plantão da madrugada sem OS e offline após as 8h deve ser FECHADO."""
        now_dt = datetime(2026, 9, 17, 11, 45, 0, tzinfo=ZoneInfo(DDS_TIMEZONE))
        rotalog_snaps = {
            # Caso E2276: plantão da madrugada, às 11:45 está sem OS e offline
            "E2276": {
                "teamKey": "E2276",
                "date": "2026-09-17",
                "conexao": {"isOnline": False, "status": "> 1h", "colaborador": "RONALDO LUAM"},
                "jornada": {
                    "emIntervalo": False,
                    "turno": {"inicio": "2026-09-17T01:57:18-03:00", "fim": None, "status": "ABERTO"},
                },
                "ordensServico": {"atual": None, "totalConcluidos": 1},
            },
            # Caso E3390: início no dia 16/09 (ontem), sem OS ativa
            "E3390": {
                "teamKey": "E3390",
                "date": "2026-09-17",
                "conexao": {"isOnline": True, "status": "online", "colaborador": "ANTONIO VALDAIR"},
                "jornada": {
                    "emIntervalo": False,
                    "turno": {"inicio": "2026-09-16T07:53:33-03:00", "fim": None, "status": "ABERTO"},
                },
                "ordensServico": {"atual": None, "totalConcluidos": 0},
            },
            # Equipe normal trabalhando hoje
            "E2146": {
                "teamKey": "E2146",
                "date": "2026-09-17",
                "conexao": {"isOnline": False, "status": "27 min", "colaborador": "MARCOS FABIANO"},
                "jornada": {
                    "emIntervalo": False,
                    "turno": {"inicio": "2026-09-17T07:29:32-03:00", "fim": None, "status": "ABERTO"},
                },
                "ordensServico": {
                    "atual": {
                        "baseDay": "2026-09-17",
                        "statusAtual": "DESLOCAMENTO",
                        "tipo": "319",
                        "protocolo": "20265734588587",
                    },
                    "totalConcluidos": 5,
                },
            },
        }

        items = _build_pure_torre_items(rotalog_snaps, now_dt)
        items_map = {it["teamKey"]: it for it in items}

        # E2276 deve estar FECHADO
        self.assertEqual(items_map["E2276"]["estado"], "FECHADO")
        self.assertEqual(items_map["E2276"]["turnStatus"], "FECHADO")

        # E3390 deve estar FECHADO (início foi ontem)
        self.assertEqual(items_map["E3390"]["estado"], "FECHADO")
        self.assertEqual(items_map["E3390"]["turnStatus"], "FECHADO")

        # E2146 deve estar ABERTO (verde no monitor)
        self.assertEqual(items_map["E2146"]["estado"], "ABERTO")
        self.assertEqual(items_map["E2146"]["turnStatus"], "ABERTO")
        self.assertEqual(items_map["E2146"]["atividadeStatusRotalog"], "DESLOCAMENTO")


if __name__ == "__main__":
    unittest.main()
