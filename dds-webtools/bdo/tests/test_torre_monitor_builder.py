import unittest
from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
MONITOR_DIR = ROOT_DIR / "monitor"
if str(MONITOR_DIR) not in sys.path:
    sys.path.insert(0, str(MONITOR_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from monitor.services.turnos_service import _build_pure_torre_items, list_turnos


class TestTorreMonitorBuilder(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 14, 17, 10, 0, tzinfo=timezone.utc)
        self.sample_snapshots = {
            "E2146": {
                "teamKey": "E2146",
                "date": "2026-09-14",
                "schemaVersion": 2,
                "updatedAt": "2026-09-14T17:10:01.636827-03:00",
                "conexao": {
                    "colaborador": "MARCOS FABIANO",
                    "identificadorEquipamento": "",
                    "isOnline": True,
                    "status": "online",
                    "veiculo": "",
                },
                "jornada": {
                    "emIntervalo": False,
                    "totalIntervalos": 1,
                    "turno": {
                        "status": "ABERTO",
                        "inicio": "2026-09-14T07:32:41-03:00",
                        "fim": None,
                        "duracaoMinutos": None,
                        "filaNaAbertura": {"comercial": 5, "emergencia": 7, "total": 12},
                    },
                },
                "ordensServico": {
                    "atual": {
                        "protocolo": "50986503",
                        "categoria": "EMERGENCIA",
                        "tipo": "UC",
                        "statusAtual": "EXECUCAO",
                        "inicioDeslocamento": "2026-09-14T16:38:00-03:00",
                        "inicioExecucao": "2026-09-14T16:38:00-03:00",
                        "latitude": -25.909619,
                        "longitude": -53.47295,
                    },
                    "totalConcluidos": 5,
                },
            },
            "E2148": {
                "teamKey": "E2148",
                "date": "2026-09-14",
                "schemaVersion": 2,
                "updatedAt": "2026-09-14T17:10:01.636827-03:00",
                "conexao": {
                    "colaborador": "JUNIOR VITOR",
                    "identificadorEquipamento": "",
                    "isOnline": True,
                    "status": "online",
                    "veiculo": "",
                },
                "jornada": {
                    "emIntervalo": False,
                    "totalIntervalos": 1,
                    "turno": {
                        "status": "ABERTO",
                        "inicio": "2026-09-14T08:00:31-03:00",
                        "fim": None,
                    },
                },
                "ordensServico": {
                    "atual": None,
                    "totalConcluidos": 8,
                },
            },
            "E2176": {
                "teamKey": "E2176",
                "date": "2026-09-14",
                "schemaVersion": 2,
                "updatedAt": "2026-09-14T17:10:01.636827-03:00",
                "conexao": {
                    "colaborador": "RODRIGO ROBSON",
                    "identificadorEquipamento": "",
                    "isOnline": False,
                    "status": "37 min",
                    "veiculo": "",
                },
                "jornada": {
                    "emIntervalo": False,
                    "totalIntervalos": 0,
                    "turno": {
                        "status": "FECHADO",
                        "inicio": "2026-09-14T07:22:56-03:00",
                        "fim": "2026-09-14T16:25:38-03:00",
                        "duracaoMinutos": 542,
                    },
                },
                "ordensServico": {
                    "atual": None,
                    "totalConcluidos": 9,
                },
            },
            "E2270": {
                "teamKey": "E2270",
                "date": "2026-09-14",
                "schemaVersion": 2,
                "updatedAt": "2026-09-14T17:10:01.636827-03:00",
                "conexao": {
                    "colaborador": "MARILDO JOAO",
                    "identificadorEquipamento": "CA228",
                    "isOnline": False,
                    "status": "> 1h",
                    "veiculo": "CA228",
                },
                "jornada": {
                    "emIntervalo": False,
                    "totalIntervalos": 1,
                    "turno": {
                        "status": "ABERTO",
                        "inicio": "2026-09-14T08:59:13-03:00",
                        "fim": None,
                    },
                },
                "ordensServico": {
                    "atual": {
                        "protocolo": "20265611128292",
                        "categoria": "COMERCIAL",
                        "tipo": "9901",
                        "statusAtual": "DESLOCAMENTO",
                        "inicioDeslocamento": "2026-09-14T15:21:00-03:00",
                        "inicioExecucao": "2026-09-14T15:21:12-03:00",
                    },
                    "totalConcluidos": 3,
                },
            },
            "E3547": {
                "teamKey": "E3547",
                "date": "2026-09-01",
                "schemaVersion": 2,
                "updatedAt": "2026-09-01T20:16:34.149410-03:00",
                "conexao": {
                    "colaborador": "ANDRE GILDANE",
                    "isOnline": False,
                    "status": "> 1h",
                },
                "jornada": {
                    "emIntervalo": False,
                    "turno": {
                        "status": "FECHADO",
                        "inicio": "2026-09-01T02:32:42-03:00",
                        "fim": "2026-09-01T15:53:41-03:00",
                    },
                },
                "ordensServico": {
                    "atual": None,
                    "totalConcluidos": 0,
                },
            },
        }

    def test_build_pure_torre_items_structure_and_states(self):
        items = _build_pure_torre_items(self.sample_snapshots, self.now)
        items_map = {it["teamKey"]: it for it in items}

        self.assertIn("E2146", items_map)
        self.assertIn("E2148", items_map)
        self.assertIn("E2176", items_map)
        self.assertIn("E2270", items_map)
        self.assertIn("E3547", items_map)

        # 1. E2146: Aberta com serviço em EXECUCAO
        e2146 = items_map["E2146"]
        self.assertEqual(e2146["estado"], "ABERTO")
        self.assertEqual(e2146["turnStatus"], "ABERTO")
        self.assertEqual(e2146["atividadeStatusRotalog"], "EXECUCAO")
        self.assertEqual(e2146["ss"], "50986503")
        self.assertEqual(e2146["totalConcluidos"], 5)
        self.assertEqual(e2146["ssExecutadasCount"], 5)
        self.assertEqual(e2146["colaborador"], "MARCOS FABIANO")
        self.assertEqual(e2146["participantes"], ["MARCOS FABIANO"])
        self.assertTrue(e2146["active"])
        self.assertEqual(e2146["origemAtualizacao"], "TORRE_CONTROLE")

        # 2. E2148: Aberta sem serviço atual (ociosa)
        e2148 = items_map["E2148"]
        self.assertEqual(e2148["estado"], "ABERTO")
        self.assertEqual(e2148["turnStatus"], "ABERTO")
        self.assertEqual(e2148["ss"], "-")
        self.assertEqual(e2148["totalConcluidos"], 8)
        self.assertTrue(e2148["active"])

        # 3. E2176: Turno FECHADO
        e2176 = items_map["E2176"]
        self.assertEqual(e2176["estado"], "FECHADO")
        self.assertEqual(e2176["turnStatus"], "FECHADO")
        self.assertEqual(e2176["totalConcluidos"], 9)
        self.assertEqual(e2176["statusConexao"], "37 min")
        self.assertFalse(e2176["isOnline"])
        self.assertTrue(e2176["active"]) # Data é de hoje (2026-09-14)

        # 4. E2270: Aberta com serviço em DESLOCAMENTO
        e2270 = items_map["E2270"]
        self.assertEqual(e2270["estado"], "ABERTO")
        self.assertEqual(e2270["turnStatus"], "ABERTO")
        self.assertEqual(e2270["atividadeStatusRotalog"], "DESLOCAMENTO")
        self.assertEqual(e2270["ss"], "20265611128292")
        self.assertEqual(e2270["veiculo"], "CA228")
        self.assertEqual(e2270["statusConexao"], "> 1h")

        # 5. E3547: Sem comunicação há mais de 7 dias (2026-09-01 vs 2026-09-14)
        e3547 = items_map["E3547"]
        self.assertFalse(e3547["active"]) # Inativa (> 7 dias)

    def test_list_turnos_with_torre_source(self):
        from unittest.mock import patch
        with patch("monitor.services.turnos_service._rotalog_json_snapshots", return_value=self.sample_snapshots), \
             patch("monitor.services.turnos_service.list_teams_map", return_value={}), \
             patch("monitor.services.turnos_service._load_today_dds_teams", return_value={}), \
             patch("monitor.services.turnos_service._load_recent_7d_dds_teams", return_value={}), \
             patch("monitor.services.turnos_service._get_now", return_value=self.now):
                # 1. Filtro active=True (equipes que comunicaram nos últimos 7 dias)
                res_active = list_turnos(empresa="ChicoEletro", active=True, manual_refresh=True)
                self.assertEqual(res_active["dataSource"], "torre_controle")
                active_keys = [it["teamKey"] for it in res_active["items"]]
                self.assertIn("E2146", active_keys)
                self.assertIn("E2148", active_keys)
                self.assertIn("E2176", active_keys)
                self.assertIn("E2270", active_keys)
                self.assertNotIn("E3547", active_keys)

                # 2. Filtro active=False (equipes inativas sem comunicação há mais de 7 dias)
                res_inactive = list_turnos(empresa="ChicoEletro", active=False, manual_refresh=True)
                inactive_keys = [it["teamKey"] for it in res_inactive["items"]]
                self.assertIn("E3547", inactive_keys)
                self.assertNotIn("E2146", inactive_keys)

                # 3. Filtro active=None (todas as equipes)
                res_all = list_turnos(empresa="ChicoEletro", active=None, manual_refresh=True)
                self.assertEqual(len(res_all["items"]), 5)

    def test_regra_7_dias_desativacao_rotalog_e_dds(self):
        from monitor.services.turnos_service import _build_pure_torre_items, _build_dds_controlled_items

        # Cenário 1: Equipes com telemetria Rotalog
        # - EQ_5D: comunicou há 5 dias (deve ser ATIVA)
        # - EQ_8D: comunicou há 8 dias sem DDS (deve ser INATIVA)
        # - EQ_8D_COM_DDS: comunicou há 8 dias no Rotalog, mas fez DDS há 2 dias (deve ser ATIVA)
        snapshots = {
            "EQ_ALPHA": {
                "teamKey": "EQ_ALPHA",
                "date": "2026-09-09",
                "updatedAt": "2026-09-09T10:00:00-03:00",
                "turno": {"status": "FECHADO", "inicio": "2026-09-09T08:00:00-03:00", "fim": "2026-09-09T17:00:00-03:00"},
            },
            "EQ_BETA": {
                "teamKey": "EQ_BETA",
                "date": "2026-09-06",
                "updatedAt": "2026-09-06T10:00:00-03:00",
                "turno": {"status": "FECHADO", "inicio": "2026-09-06T08:00:00-03:00", "fim": "2026-09-06T17:00:00-03:00"},
            },
            "EQ_GAMA": {
                "teamKey": "EQ_GAMA",
                "date": "2026-09-06",
                "updatedAt": "2026-09-06T10:00:00-03:00",
                "turno": {"status": "FECHADO", "inicio": "2026-09-06T08:00:00-03:00", "fim": "2026-09-06T17:00:00-03:00"},
            },
        }
        recent_dds = {
            "EQ_GAMA": {"completedAt": "2026-09-12T07:15:00-03:00", "date": "2026-09-12"},
            "EQ_DDS_ONLY": {"completedAt": "2026-09-13T07:10:00-03:00", "date": "2026-09-13"},
        }

        pure_items = _build_pure_torre_items(snapshots, self.now, recent_7d_dds=recent_dds)
        pure_map = {it["teamKey"]: it for it in pure_items}

        self.assertTrue(pure_map["EQ_ALPHA"]["active"], "EQ_ALPHA comunicou há 5 dias, deve ser ativa")
        self.assertFalse(pure_map["EQ_BETA"]["active"], "EQ_BETA comunicou há 8 dias sem DDS, deve ser inativa")
        self.assertTrue(pure_map["EQ_GAMA"]["active"], "EQ_GAMA fez DDS nos últimos 7 dias, deve ser ativa")
        self.assertEqual(pure_map["EQ_GAMA"]["lastContactSource"], "D")

        # Cenário 2: Equipes sem telemetria (controladas por DDS / cadastro)
        # - EQ_DDS_ONLY: fez DDS há 1 dia (sem DDS hoje) -> deve ser ATIVA, turno FECHADO
        # - EQ_SEM_NADA: não fez DDS nos últimos 7 dias -> deve ser INATIVA
        from unittest.mock import patch
        with patch("monitor.services.turnos_service._load_today_dds_teams", return_value={}):
            teams_map = {
                "EQ_DDS_ONLY": {"displayName": "Equipe DDS Only"},
                "EQ_SEM_NADA": {"displayName": "Equipe Sem Nada"},
            }
            dds_items = _build_dds_controlled_items(
                telemetry_keys=set(pure_map.keys()),
                now=self.now,
                teams_map=teams_map,
                recent_7d_dds=recent_dds,
            )
            dds_map = {it["teamKey"]: it for it in dds_items}

            self.assertTrue(dds_map["EQ_DDS_ONLY"]["active"], "EQ_DDS_ONLY tem DDS nos últimos 7 dias, deve ser ativa")
            self.assertEqual(dds_map["EQ_DDS_ONLY"]["estado"], "FECHADO")
            self.assertEqual(dds_map["EQ_DDS_ONLY"]["lastContactSource"], "D")

            self.assertFalse(dds_map["EQ_SEM_NADA"]["active"], "EQ_SEM_NADA não tem sinal nem DDS há 7 dias, deve ser inativa")


if __name__ == "__main__":
    unittest.main()

