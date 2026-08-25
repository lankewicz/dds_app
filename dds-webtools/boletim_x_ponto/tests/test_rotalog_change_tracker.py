import json
import os
import tempfile
import unittest

from boletim_x_ponto.services.rotalog_change_tracker import (
    RotalogLocalCache,
    changed_fields,
    compact_snapshot,
)
from boletim_x_ponto.services.rotalog_sync_task import (
    _deve_aplicar_estado_rotalog,
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


class RotalogChangeTrackerTests(unittest.TestCase):
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
