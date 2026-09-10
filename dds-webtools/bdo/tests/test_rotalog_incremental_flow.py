import copy
import datetime
import os
import tempfile
import unittest
from unittest import mock

from bdo.services import rotalog_sync_task as sync
from bdo.services.rotalog_change_tracker import RotalogLocalCache, RotalogGcsSnapshotStore, changed_fields
from bdo.services.rotalog_tempo_real_service import _enriquecer_com_snapshot_anterior, _servico_precisa_detalhes
from bdo.services.rotalog_daily_reconciliation import normalize_events, normalize_turns, reconcile_document
from bdo.services.rotalog_team_file_repository import RotalogTeamFileRepository


class IncrementalFlowTests(unittest.TestCase):
    def test_snapshot_preserves_new_times_and_known_protocol(self):
        service = {"inicioIso": "2026-09-10T09:00:00-03:00", "tipo": "UC",
                   "protocolo": "UC", "termino": "10:30", "status": "CONCLUSAO"}
        previous = {**service, "protocolo": "50961067", "termino": "10:00",
                    "detalhesStatus": "EXECUCAO"}
        _enriquecer_com_snapshot_anterior(
            [{"equipe_codigo": "E3389", "ss_executadas": [service]}],
            {"E3389": {"ssEmAndamento": [previous]}})
        self.assertEqual("10:30", service["termino"])
        self.assertEqual("50961067", service["protocolo"])
        self.assertTrue(_servico_precisa_detalhes(service))

    def test_completed_details_need_no_popup(self):
        service = {"protocolo": "50961067", "status": "CONCLUSAO",
                   "detalhesStatus": "CONCLUSAO", "inicioDeslocamento": "09:00",
                   "inicioExecucao": "09:10", "termino": "10:30", "retorno": "10:40"}
        self.assertFalse(_servico_precisa_detalhes(service))
        service["inicioExecucao"] = None
        self.assertTrue(_servico_precisa_detalhes(service))

    def test_diff_ignores_position_and_order_but_tracks_connection(self):
        first = {"ssExecutadas": [{"protocolo": "50961067", "eventIdx": 1},
                                 {"protocolo": "50961068", "eventIdx": 2}]}
        second = {"ssExecutadas": [{"protocolo": "50961068", "eventIdx": 40},
                                  {"protocolo": "50961067", "eventIdx": 42}]}
        self.assertFalse(changed_fields(first, second))
        self.assertIn("isOnline", changed_fields({"isOnline": True}, {"isOnline": False}))

    def test_reader_refreshes_snapshot_from_other_process(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = RotalogLocalCache(os.path.join(directory, "cache.json"))
            cache.replace({"E3389": {"version": 1}})
            store = mock.Mock(enabled=True)
            store.load.return_value = {"snapshots": {"E3389": {"version": 2}}}
            with mock.patch.object(sync, "_local_cache", cache), mock.patch.object(sync, "_durable_cache_store", store), mock.patch.object(sync, "_durable_cache_state", {"hydrated": True, "loaded_at": 0, "reads": 0}):
                sync._hydrate_durable_cache_once()
                self.assertEqual(2, cache.get("E3389")["version"])
                sync._hydrate_durable_cache_once()
                self.assertEqual(1, store.load.call_count)

    def _persist(self, cache, repo, store, publication=True):
        eq = {"equipe_codigo": "E3389", "estado_consolidado": "ABERTO",
              "turno": {}, "ss_executadas": [], "ss_em_andamento": []}
        with mock.patch.object(sync, "_local_cache", cache), mock.patch.object(sync, "_team_file_repository", repo), mock.patch.object(sync, "_durable_cache_store", store), mock.patch.object(sync, "_persist_durable_cache", return_value=publication):
            return sync._persistir_somente_json(
                [eq], "ChicoEletro", "2026-09-11T03:05:00+00:00", {},
                gcs_reads_before=0, gcs_writes_before=0, firestore_reads=0)

    def test_failed_team_write_is_not_acknowledged(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = RotalogLocalCache(os.path.join(directory, "cache.json"))
            repo = mock.Mock()
            repo.merge_and_save_daily.side_effect = IOError("storage failed")
            with self.assertRaises(IOError):
                self._persist(cache, repo, mock.Mock(enabled=True))
            self.assertIsNone(cache.get("E3389"))

    def test_failed_index_publication_rolls_back_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = RotalogLocalCache(os.path.join(directory, "cache.json"))
            with self.assertRaises(RuntimeError):
                self._persist(cache, mock.Mock(), mock.Mock(enabled=True), publication=False)
            self.assertIsNone(cache.get("E3389"))

    def test_new_day_writes_unchanged_team_and_current(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = RotalogLocalCache(os.path.join(directory, "cache.json"))
            repo = mock.Mock()
            store = mock.Mock(enabled=True)
            self._persist(cache, repo, store)
            previous = cache.get("E3389")
            previous["historyDay"] = "2026-09-10"
            cache.set("E3389", previous)
            repo.reset_mock()
            self._persist(cache, repo, store)
            self.assertEqual("2026-09-11", repo.merge_and_save_daily.call_args.args[1])
            repo.save_current.assert_called_once()

    def test_daily_reader_observes_other_writer(self):
        store = mock.Mock()
        store.load_blob.side_effect = [{"version": 1}, {"version": 2}]
        repo = RotalogTeamFileRepository(store)
        self.assertEqual(1, repo.load_daily("E3389", "2026-09-10")["version"])
        self.assertEqual(2, repo.load_daily("E3389", "2026-09-10")["version"])

    def test_shared_lease_has_single_owner_and_owner_checked_release(self):
        class MemoryStore(RotalogGcsSnapshotStore):
            def __init__(self):
                super().__init__("bucket", "dados/chicoeletro/rotalog/equipes/current/index.json.gz")
                self.record = {}
            def update_blob(self, path, transform):
                self.record = transform(self.record)
                return self.record
        store = MemoryStore()
        token = store.acquire_sync_lease()
        self.assertTrue(token)
        self.assertIsNone(store.acquire_sync_lease())
        store.release_sync_lease("wrong-owner")
        self.assertIsNone(store.acquire_sync_lease())
        store.release_sync_lease(token)
        self.assertTrue(store.acquire_sync_lease())


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.day = "2026-09-10"
        self.old = {"teamKey": "E3389", "date": self.day, "turno": {},
                    "services": [{"serviceId": "E3389_abc", "tipo": "UC", "protocolo": "UC",
                                  "inicioExecucao": self.day + "T09:00:00-03:00",
                                  "fimExecucao": self.day + "T10:30:00-03:00"}]}
        self.rows = [{"Veículo": "E3389", "Protocolo": "50961067", "Código": "UC",
                      "Inicio Exec": "10/09/2026 09:00", "Fim Exec": "10/09/2026 10:00",
                      "Retorno": "10/09/2026 10:40"}]
        self.events = normalize_events(self.rows, self.day)["E3389"]

    def test_fills_missing_only_and_is_idempotent(self):
        new = reconcile_document(self.old, self.events, self.day, "first")
        self.assertEqual("E3389_abc", new["services"][0]["serviceId"])
        self.assertEqual("50961067", new["services"][0]["protocolo"])
        self.assertEqual(self.old["services"][0]["fimExecucao"], new["services"][0]["fimExecucao"])
        self.assertEqual(new, reconcile_document(new, self.events, self.day, "second"))
        self.assertEqual("UC", self.old["services"][0]["protocolo"])

    def test_ambiguous_match_and_other_date_do_not_change_history(self):
        ambiguous = [*self.events, {**self.events[0], "protocolo": "50961068"}]
        self.assertEqual(self.old, reconcile_document(self.old, ambiguous, self.day, "now"))
        self.assertEqual(self.old, reconcile_document(self.old, self.events, "2026-09-09", "now"))

    def test_known_protocol_conflict_is_preserved(self):
        self.old["services"][0]["protocolo"] = "50961999"
        self.assertEqual(self.old, reconcile_document(self.old, self.events, self.day, "now"))

    def test_unique_turn_fills_missing_end_only(self):
        turns = normalize_turns([{"Veículo": "E3389", "Inicio Turno": "10/09/2026 08:00",
                                  "Fim Turno": "10/09/2026 18:00"}], self.day)
        self.old["turno"]["inicio"] = self.day + "T07:00:00-03:00"
        new = reconcile_document(self.old, [], self.day, "now", turns["E3389"])
        self.assertEqual(self.old["turno"]["inicio"], new["turno"]["inicio"])
        self.assertTrue(new["turno"]["fim"].endswith("18:00:00-03:00"))

    def test_cross_midnight_preserves_full_source_date(self):
        rows = [{**self.rows[0], "Retorno": "11/09/2026 00:10"}]
        event = normalize_events(rows, self.day)["E3389"][0]
        self.assertEqual("2026-09-11T00:10:00-03:00", event["retorno"])

    def test_commercial_protocol_keeps_identifier_between_prefix_and_suffix(self):
        rows = [{**self.rows[0], "Protocolo": "01.20265507121122.1.1"}]
        event = normalize_events(rows, self.day)["E3389"][0]
        self.assertEqual("20265507121122", event["protocolo"])
