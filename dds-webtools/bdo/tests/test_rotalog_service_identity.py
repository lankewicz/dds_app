import unittest
from bdo.services.rotalog_team_file_repository import _merge_service_records
from bdo.services.rotalog_tempo_real_service import _enriquecer_com_snapshot_anterior


class ServiceIdentityTests(unittest.TestCase):
    def service(self, sid="a", protocol="50961067", start="10:00", **extra):
        return {"serviceId": "E3D97_" + sid, "protocolo": protocol,
                "inicioDeslocamento": "2026-09-08T" + start + ":00-03:00",
                "tipo": "UC", **extra}

    def test_different_protocols_same_time(self):
        records = [self.service(), self.service(protocol="50961068")]
        self.assertEqual(2, len(_merge_service_records("E3D97", records)))

    def test_same_protocol_different_time(self):
        self.assertEqual(2, len(_merge_service_records("E3D97",
            [self.service(), self.service(start="11:00")])))

    def test_exact_key_merges_and_preserves_fields(self):
        records = [self.service(latitude=-25), self.service(sid="b", tipo="CHAVE")]
        result = list(_merge_service_records("E3D97", records).values())
        self.assertEqual(1, len(result))
        self.assertEqual(-25, result[0]["latitude"])
        self.assertEqual(["UC", "CHAVE"], result[0]["historicoTipos"])

    def test_missing_protocol_requires_same_id(self):
        self.assertEqual(2, len(_merge_service_records("E3D97",
            [self.service(protocol=None), self.service(sid="b", protocol=None)])))
        result = list(_merge_service_records("E3D97",
            [self.service(protocol=None), self.service()]).values())
        self.assertEqual(1, len(result))
        self.assertEqual("50961067", result[0]["protocolo"])

    def test_other_team_rejected(self):
        with self.assertRaises(ValueError):
            _merge_service_records("E3552", [self.service()])

    def test_old_update_does_not_replace_recent(self):
        records = [
            self.service(tipo="CHAVE", observadoEm="2026-09-08T12:00:00-03:00"),
            self.service(tipo="UC", observadoEm="2026-09-08T11:00:00-03:00"),
        ]
        result = list(_merge_service_records("E3D97", records).values())
        self.assertEqual("CHAVE", result[0]["tipo"])

    def test_reuses_unique_protocol_from_previous_snapshot(self):
        current = {
            "equipe_codigo": "E3D97",
            "ss_executadas": [{
                "inicioIso": "2026-09-10T09:00:00-03:00",
                "tipo": "UC",
                "protocolo": "UC",
            }],
            "ss_em_andamento": [],
        }
        previous = {
            "E3D97": {
                "ssExecutadas": [{
                    "inicioIso": "2026-09-10T09:00:00-03:00",
                    "tipo": "UC",
                    "protocolo": "50961067",
                    "latitude": -25.4,
                }],
                "ssEmAndamento": [],
            }
        }

        resolved = _enriquecer_com_snapshot_anterior([current], previous)

        self.assertEqual(1, resolved)
        self.assertEqual("50961067", current["ss_executadas"][0]["protocolo"])
        self.assertEqual("SNAPSHOT_ANTERIOR", current["ss_executadas"][0]["fonteProtocolo"])

    def test_does_not_reuse_ambiguous_previous_snapshot(self):
        service = {
            "inicioIso": "2026-09-10T09:00:00-03:00",
            "tipo": "UC",
            "protocolo": "UC",
        }
        current = {
            "equipe_codigo": "E3D97",
            "ss_executadas": [service],
            "ss_em_andamento": [],
        }
        duplicate = {
            "inicioIso": service["inicioIso"],
            "tipo": "UC",
            "protocolo": "50961067",
        }
        previous = {
            "E3D97": {
                "ssExecutadas": [duplicate, {**duplicate, "protocolo": "50961068"}],
                "ssEmAndamento": [],
            }
        }

        resolved = _enriquecer_com_snapshot_anterior([current], previous)

        self.assertEqual(0, resolved)
        self.assertEqual("UC", service["protocolo"])
