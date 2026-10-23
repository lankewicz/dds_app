import datetime
import datetime
import json
import os
import tempfile
import unittest
from unittest import mock

from bdo.services.rotalog_change_tracker import (
    RotalogLocalCache,
    changed_fields,
    compact_snapshot,
)
from bdo.services.rotalog_change_tracker import RotalogGcsSnapshotStore
from bdo.services.rotalog_team_file_repository import LOCAL_TZ


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










if __name__ == "__main__":
    unittest.main()
