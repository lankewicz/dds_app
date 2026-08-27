import datetime
import json
import os
import tempfile
import unittest
from unittest import mock

from boletim_x_ponto.services.rotalog_change_tracker import (
    RotalogLocalCache,
    changed_fields,
    compact_snapshot,
)
from boletim_x_ponto.services.rotalog_change_tracker import RotalogGcsSnapshotStore
from boletim_x_ponto.services.rotalog_sync_task import (
    _build_team_base_payload,
    _deve_aplicar_estado_rotalog,
    _describe_rotalog_change,
    _executar_sincronizacao_rotalog,
    _service_id,
    _sync_execution_lock,
    executar_sincronizacao_rotalog,
)


def _document(status="ABERTO"):
    return {
        "estadoConsolidado": status,
        "turno": {"inicio_ms": 1, "fim_ms": None},
        "intervalo": {"em_intervalo": False},
        "atividadeAtual": {"status": "EXECUCAO", "tipo": "191"},
        "ssExecutadas": [],
        "ssEmAndamento": [{"status": "EXECUCAO", "tipo": "191"}],
        "ssPendentes": [],
        "updatedAtIso": "nao-faz-parte-da-assinatura",
    }


class _FakeBlob:
    def __init__(self):
        self.data = None
        self.content_encoding = None
        self.uploads = 0
        self.downloads = 0

    def upload_from_string(self, data, content_type=None):
        self.data = data
        self.content_type = content_type
        self.uploads += 1

    def download_as_bytes(self):
        self.downloads += 1
        return self.data


class _FakeBucket:
    def __init__(self, blob):
        self._blob = blob

    def blob(self, name):
        self.name = name
        return self._blob


class _FakeStorageClient:
    def __init__(self, blob):
        self._bucket = _FakeBucket(blob)

    def bucket(self, name):
        self.name = name
        return self._bucket


class RotalogChangeTrackerTests(unittest.TestCase):
    def test_id_servico_nao_muda_quando_protocolo_e_enriquecido(self):
        base = {
            "tipo": "192",
            "inicioIso": "2026-08-26T14:04:00+00:00",
            "fimIso": "2026-08-26T14:40:00+00:00",
        }
        sem_protocolo = {**base, "ssId": "", "protocoloBruto": ""}
        com_protocolo = {
            **base,
            "ssId": "20265445297154",
            "protocoloBruto": "20265445297154.1.1",
        }
        self.assertEqual(
            _service_id("E2270", sem_protocolo),
            _service_id("E2270", com_protocolo),
        )
    def test_snapshot_gcs_gzip_roundtrip(self):
        blob = _FakeBlob()
        store = RotalogGcsSnapshotStore(
            "bucket-teste",
            "_cache/rotalog.json.gz",
            client_factory=lambda: _FakeStorageClient(blob),
        )
        expected = {"E3X93": compact_snapshot(_document())}
        store.save(expected)
        self.assertEqual(store.load(), expected)
        self.assertEqual(blob.content_encoding, "gzip")
        self.assertEqual(blob.content_type, "application/json")
        self.assertEqual(blob.uploads, 1)
        self.assertEqual(blob.downloads, 1)
    def test_snapshot_gcs_serializa_timestamp_firestore_como_iso(self):
        blob = _FakeBlob()
        store = RotalogGcsSnapshotStore(
            "bucket-teste",
            "_cache/rotalog.json.gz",
            client_factory=lambda: _FakeStorageClient(blob),
        )
        timestamp = datetime.datetime(2026, 8, 26, 14, 38, 4, tzinfo=datetime.timezone.utc)
        store.save({"teamDocs": {"E2270": {"updatedAt": timestamp}}})
        loaded = store.load()
        self.assertEqual(loaded["teamDocs"]["E2270"]["updatedAt"], timestamp.isoformat())
    def test_leitura_igual_nao_gera_mudanca(self):
        snapshot = compact_snapshot(_document())
        self.assertEqual(changed_fields(snapshot, snapshot), {})

    def test_mudanca_de_estado_gera_diff_compacto(self):
        previous = compact_snapshot(_document("ABERTO"))
        current = compact_snapshot(_document("FECHADO"))
        self.assertEqual(changed_fields(previous, current), {
            "estadoConsolidado": {"anterior": "ABERTO", "novo": "FECHADO"}
        })

    def test_cache_persiste_e_recupera_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "rotalog.json")
            cache = RotalogLocalCache(path)
            snapshot = compact_snapshot(_document())
            cache.set("E2269", snapshot)

            reloaded = RotalogLocalCache(path)
            self.assertEqual(reloaded.get("E2269"), snapshot)
            with open(path, "r", encoding="utf-8") as stream:
                self.assertEqual(json.load(stream)["E2269"], snapshot)

    def test_cadastro_igual_nao_gera_gravacao(self):
        eq = {"identificador_equipamento": "CA226", "estado_consolidado": "ABERTO", "turno": {"aberto": True}}
        current = {
            "currentTablet": "CA226", "rotalogTablet": "CA226", "tablet": "CA226",
            "equipment": {"tablet": {"identifier": "CA226", "kind": "tablet", "label": "Tablet"}},
            "active": True, "teamKey": "E3X93", "equipe": "E3X93",
            "deactivatedReason": None, "reactivatedBy": "ROTALOG_AUTO_SYNC",
        }
        self.assertEqual(_build_team_base_payload(eq, "E3X93", "E3X93", current), {})

    def test_cadastro_grava_somente_campos_alterados(self):
        eq = {"identificador_equipamento": "CA226", "estado_consolidado": "ABERTO", "turno": {"aberto": True}}
        current = {
            "currentTablet": "CA226", "rotalogTablet": "CA226", "tablet": "CA226",
            "equipment": {"tablet": {"identifier": "CA226", "kind": "tablet", "label": "Tablet"}},
            "active": False, "teamKey": "E3X93", "equipe": "E3X93",
            "deactivatedReason": "MANUAL", "reactivatedBy": "ROTALOG_AUTO_SYNC",
        }
        self.assertEqual(
            _build_team_base_payload(eq, "E3X93", "E3X93", current),
            {"active": True, "deactivatedReason": None},
        )
    def test_feed_descreve_equipe_tipo_e_status_do_servico(self):
        previous = {
            "teamKey": "E3X99",
            "estadoConsolidado": "ABERTO",
            "atividadeAtual": {"tipo": "9925", "status": "DESLOCAMENTO"},
        }
        current = {
            "teamKey": "E3X99",
            "estadoConsolidado": "ABERTO",
            "atividadeAtual": {"tipo": "9925", "status": "EXECUCAO"},
        }
        changes = changed_fields(previous, current)
        self.assertEqual(
            _describe_rotalog_change(previous, current, changes),
            "E3X99 - 9925 - EXECUCAO",
        )

    def test_feed_descreve_abertura_e_fechamento(self):
        previous = {"teamKey": "E3X99", "estadoConsolidado": "ABERTO"}
        current = {"teamKey": "E3X99", "estadoConsolidado": "FECHADO"}
        changes = changed_fields(previous, current)
        self.assertEqual(
            _describe_rotalog_change(previous, current, changes),
            "E3X99 - ABERTO → FECHADO",
        )
    def test_modo_json_nao_cria_batch_nem_operacoes_firestore(self):
        equipe = {
            "equipe_codigo": "E3389",
            "group_raw": "E3389- TESTE (online)",
            "veiculo": "",
            "identificador_equipamento": "CA389",
            "origem_resolucao": "PREFIXO_EQUIPE",
            "colaborador": "TESTE",
            "status_conexao": "online",
            "is_online": True,
            "estado_consolidado": "ABERTO",
            "turno": {"aberto": True, "inicio_ms": 1000, "fim_ms": None},
            "intervalo": {"em_intervalo": False, "inicio_ms": None, "fim_ms": None},
            "atividade_atual": None,
            "bdo_list": [],
            "ss_executadas": [],
            "ss_em_andamento": [],
            "ss_pendentes": [{"sequencia": "1", "tipo": "COMERCIAL"}],
        }

        class DbSemEscrita:
            def batch(self):
                raise AssertionError("batch Firestore não pode ser criado no modo JSON")

        with tempfile.TemporaryDirectory() as directory:
            cache = RotalogLocalCache(os.path.join(directory, "rotalog.json"))
            with (
                mock.patch("boletim_x_ponto.services.rotalog_sync_task._ROTALOG_PERSISTENCE_MODE", "json"),
                mock.patch("boletim_x_ponto.services.rotalog_sync_task._local_cache", cache),
                mock.patch("boletim_x_ponto.services.rotalog_sync_task.get_firestore_client", return_value=DbSemEscrita()),
                mock.patch("boletim_x_ponto.services.rotalog_sync_task._hydrate_durable_cache_once"),
                mock.patch("boletim_x_ponto.services.rotalog_sync_task._get_equipment_identifier_index", return_value={}),
                mock.patch("boletim_x_ponto.services.rotalog_sync_task.extrair_dados_tempo_real", return_value=[equipe]),
                mock.patch("boletim_x_ponto.services.rotalog_sync_task._persist_durable_cache", return_value=True),
            ):
                result = _executar_sincronizacao_rotalog()

        self.assertEqual(result["persistenceMode"], "json")
        self.assertEqual(result["leiturasFirestore"], 0)
        self.assertEqual(result["gravacoesFirestore"], 0)
        self.assertEqual(result["equipesAtualizadasJson"], 1)
        self.assertEqual(result["servicosPendentesPorEquipe"]["E3389"]["comercial"], 1)
    def test_sincronizacao_concorrente_e_ignorada(self):
        _sync_execution_lock.acquire()
        try:
            result = executar_sincronizacao_rotalog()
        finally:
            _sync_execution_lock.release()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "sync_already_running")

    def test_estado_manual_mais_recente_e_preservado(self):
        dds = {
            "estado": "FECHADO",
            "clientUpdatedAtMs": 2000,
            "deviceIdLastWriter": "TABLET-01",
        }
        self.assertFalse(_deve_aplicar_estado_rotalog("ABERTO", 1000, dds, True))

    def test_estado_do_rotalog_pode_se_autorreparar(self):
        dds = {
            "estado": "DESATUALIZADO",
            "clientUpdatedAtMs": 2000,
            "deviceIdLastWriter": "ROTALOG_AUTO_SYNC",
        }
        self.assertTrue(_deve_aplicar_estado_rotalog("ABERTO", 2000, dds, True))

    def test_reconciliacao_forcada_repara_estado_antigo_do_rotalog(self):
        dds = {
            "estado": "DESATUALIZADO",
            "clientUpdatedAtMs": 3000,
            "deviceIdLastWriter": "ROTALOG_AUTO_SYNC",
        }
        self.assertTrue(
            _deve_aplicar_estado_rotalog("ABERTO", 2000, dds, True, forcar=True)
        )

    def test_reconciliacao_forcada_nao_ignora_estado_manual_mais_recente(self):
        dds = {
            "estado": "FECHADO",
            "clientUpdatedAtMs": 3000,
            "deviceIdLastWriter": "TABLET-01",
        }
        self.assertFalse(
            _deve_aplicar_estado_rotalog("ABERTO", 2000, dds, True, forcar=True)
        )


if __name__ == "__main__":
    unittest.main()
